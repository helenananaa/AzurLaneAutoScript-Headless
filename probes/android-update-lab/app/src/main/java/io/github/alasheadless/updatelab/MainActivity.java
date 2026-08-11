package io.github.alasheadless.updatelab;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.StatFs;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.RandomAccessFile;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

public final class MainActivity extends Activity {
    private static final String TAG = "ALAS_UPDATE_LAB";
    private static final String PREFS = "update-lab";
    private static final String INTERNAL_SENTINEL = "internal-sentinel.txt";
    private static final String EXTERNAL_SENTINEL = "external-sentinel.txt";
    private static final String STATUS_FILE = "status.json";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        migrateIfNeeded();
        Intent intent = getIntent();
        String operation = intent.getStringExtra("operation");
        if (operation == null || operation.trim().isEmpty()) {
            operation = "status";
        }
        try {
            if ("initialize".equals(operation)) {
                initialize(intent.getStringExtra("sentinel"));
                emit(status("initialized", null));
                finish();
            } else if ("download".equals(operation)) {
                startDownload(intent);
            } else if ("promote".equals(operation)) {
                promote(intent.getIntExtra("epoch", -1), intent.getStringExtra("sha256"));
                emit(status("promoted", null));
                finish();
            } else if ("status".equals(operation)) {
                emit(status("status", null));
                finish();
            } else {
                emit(status("failed", "unsupported-operation"));
                finish();
            }
        } catch (Exception error) {
            emit(status("failed", failureCode(error)));
            finish();
        }
    }

    private void migrateIfNeeded() {
        SharedPreferences preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        int prior = preferences.getInt("schema", 0);
        int target = BuildConfig.VERSION_CODE >= 2 ? 2 : 1;
        if (prior > 0 && prior < target) {
            preferences.edit()
                .putInt("schema", target)
                .putString("migration", "schema-" + prior + "-to-" + target)
                .commit();
        }
    }

    private void initialize(String requestedSentinel) throws Exception {
        String sentinel = requestedSentinel;
        if (sentinel == null || sentinel.trim().isEmpty()) {
            sentinel = "alas-update-lab-sentinel";
        }
        writeAtomic(new File(getFilesDir(), INTERNAL_SENTINEL), sentinel + "\n");
        writeAtomic(new File(requireExternalRoot(), EXTERNAL_SENTINEL), sentinel + "\n");
        getSharedPreferences(PREFS, MODE_PRIVATE).edit()
            .putInt("schema", BuildConfig.VERSION_CODE >= 2 ? 2 : 1)
            .putString("sentinel", sentinel)
            .commit();
    }

    private void startDownload(Intent intent) {
        final String url = intent.getStringExtra("url");
        final String expectedHash = normalizedHash(intent.getStringExtra("sha256"));
        final int epoch = intent.getIntExtra("epoch", -1);
        final long requiredFreeBytes = intent.getLongExtra("required_free_bytes", 0L);
        final int chunkDelayMs = Math.max(0, intent.getIntExtra("chunk_delay_ms", 0));
        if (url == null || url.trim().isEmpty() || expectedHash == null || epoch < 1) {
            emit(status("failed", "invalid-download-request"));
            finish();
            return;
        }
        Thread worker = new Thread(() -> {
            try {
                download(url, expectedHash, epoch, requiredFreeBytes, chunkDelayMs);
                emit(status("downloaded", null));
            } catch (Exception error) {
                emit(status("failed", failureCode(error)));
            } finally {
                runOnUiThread(this::finish);
            }
        }, "alas-update-download");
        worker.start();
    }

    private void download(
        String urlText,
        String expectedHash,
        int epoch,
        long requiredFreeBytes,
        int chunkDelayMs
    ) throws Exception {
        File root = requireExternalRoot();
        StatFs stat = new StatFs(root.getAbsolutePath());
        if (requiredFreeBytes > 0 && stat.getAvailableBytes() < requiredFreeBytes) {
            throw new IllegalStateException("low-space");
        }
        File partial = new File(root, "resource-epoch-" + epoch + ".bin.part");
        File complete = new File(root, "resource-epoch-" + epoch + ".bin");
        long existing = partial.isFile() ? partial.length() : 0L;
        HttpURLConnection connection = (HttpURLConnection) new URL(urlText).openConnection();
        connection.setConnectTimeout(10000);
        connection.setReadTimeout(10000);
        connection.setRequestProperty("Accept-Encoding", "identity");
        if (existing > 0) {
            connection.setRequestProperty("Range", "bytes=" + existing + "-");
        }
        int response = connection.getResponseCode();
        if (existing > 0 && response == HttpURLConnection.HTTP_OK) {
            if (!partial.delete()) {
                throw new IllegalStateException("partial-reset-failed");
            }
            existing = 0L;
        } else if (response != HttpURLConnection.HTTP_OK &&
                   response != HttpURLConnection.HTTP_PARTIAL) {
            throw new IllegalStateException("http-" + response);
        }
        try (BufferedInputStream input = new BufferedInputStream(connection.getInputStream());
             RandomAccessFile output = new RandomAccessFile(partial, "rw")) {
            output.seek(existing);
            byte[] buffer = new byte[64 * 1024];
            int read;
            long sinceSync = 0L;
            while ((read = input.read(buffer)) != -1) {
                output.write(buffer, 0, read);
                sinceSync += read;
                if (sinceSync >= 1024L * 1024L) {
                    output.getFD().sync();
                    sinceSync = 0L;
                    writeDownloadStatus(epoch, partial.length(), false);
                }
                if (chunkDelayMs > 0) {
                    Thread.sleep(chunkDelayMs);
                }
            }
            output.getFD().sync();
        } finally {
            connection.disconnect();
        }
        String actualHash = sha256(partial);
        if (!expectedHash.equals(actualHash)) {
            throw new IllegalStateException("sha256-mismatch");
        }
        if (complete.exists() && !complete.delete()) {
            throw new IllegalStateException("old-complete-delete-failed");
        }
        if (!partial.renameTo(complete)) {
            throw new IllegalStateException("resource-promote-rename-failed");
        }
        writeDownloadStatus(epoch, complete.length(), true);
    }

    private void promote(int epoch, String requestedHash) throws Exception {
        String expectedHash = normalizedHash(requestedHash);
        if (epoch < 1 || expectedHash == null) {
            throw new IllegalArgumentException("invalid-promotion-request");
        }
        File complete = new File(requireExternalRoot(), "resource-epoch-" + epoch + ".bin");
        if (!complete.isFile() || !expectedHash.equals(sha256(complete))) {
            throw new IllegalStateException("promotion-artifact-mismatch");
        }
        JSONObject pointer = new JSONObject();
        pointer.put("epoch", epoch);
        pointer.put("sha256", expectedHash);
        pointer.put("bytes", complete.length());
        writeAtomic(new File(requireExternalRoot(), "active-resource.json"), pointer + "\n");
    }

    private JSONObject status(String outcome, String failure) {
        JSONObject result = new JSONObject();
        try {
            SharedPreferences preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
            File root = requireExternalRoot();
            result.put("schema", "alas-headless.android-update-lab-status/v1");
            result.put("outcome", outcome);
            result.put("failure", failure == null ? JSONObject.NULL : failure);
            result.put("package", getPackageName());
            result.put("version_code", BuildConfig.VERSION_CODE);
            result.put("version_name", BuildConfig.VERSION_NAME);
            result.put("data_schema", preferences.getInt("schema", 0));
            result.put("migration", preferences.getString("migration", ""));
            result.put("sentinel", preferences.getString("sentinel", ""));
            result.put("internal_sentinel", readText(new File(getFilesDir(), INTERNAL_SENTINEL)));
            result.put("external_sentinel", readText(new File(root, EXTERNAL_SENTINEL)));
            result.put("active_resource", readJsonOrNull(new File(root, "active-resource.json")));
            JSONArray resources = new JSONArray();
            File[] files = root.listFiles();
            if (files != null) {
                for (File file : files) {
                    if (file.getName().startsWith("resource-epoch-")) {
                        JSONObject item = new JSONObject();
                        item.put("name", file.getName());
                        item.put("bytes", file.length());
                        resources.put(item);
                    }
                }
            }
            result.put("resources", resources);
            result.put("available_bytes", new StatFs(root.getAbsolutePath()).getAvailableBytes());
        } catch (Exception error) {
            try {
                result.put("status_error", error.getClass().getSimpleName());
            } catch (Exception ignored) {
                // JSONObject insertion cannot fail for these values.
            }
        }
        return result;
    }

    private void writeDownloadStatus(int epoch, long bytes, boolean complete) throws Exception {
        JSONObject progress = new JSONObject();
        progress.put("schema", "alas-headless.android-update-lab-progress/v1");
        progress.put("epoch", epoch);
        progress.put("bytes", bytes);
        progress.put("complete", complete);
        writeAtomic(new File(requireExternalRoot(), STATUS_FILE), progress + "\n");
    }

    private void emit(JSONObject value) {
        try {
            writeAtomic(new File(requireExternalRoot(), STATUS_FILE), value + "\n");
        } catch (Exception error) {
            Log.e(TAG, "status-write-failed", error);
        }
        Log.i(TAG, "ALAS_UPDATE_LAB " + value);
    }

    private File requireExternalRoot() {
        File root = getExternalFilesDir(null);
        if (root == null) {
            throw new IllegalStateException("external-storage-unavailable");
        }
        if (!root.isDirectory() && !root.mkdirs()) {
            throw new IllegalStateException("external-storage-create-failed");
        }
        return root;
    }

    private static String normalizedHash(String value) {
        if (value == null) {
            return null;
        }
        String normalized = value.trim().toLowerCase(Locale.ROOT);
        return normalized.matches("[0-9a-f]{64}") ? normalized : null;
    }

    private static String failureCode(Exception error) {
        String message = error.getMessage();
        if (message != null && message.matches("[a-z0-9-]+")) {
            return message;
        }
        return error.getClass().getSimpleName();
    }

    private static String sha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (BufferedInputStream input = new BufferedInputStream(new FileInputStream(file))) {
            byte[] buffer = new byte[1024 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
            }
        }
        StringBuilder result = new StringBuilder();
        for (byte value : digest.digest()) {
            result.append(String.format(Locale.ROOT, "%02x", value & 0xff));
        }
        return result.toString();
    }

    private static void writeAtomic(File destination, String text) throws Exception {
        File temporary = new File(destination.getParentFile(), destination.getName() + ".tmp");
        try (FileOutputStream output = new FileOutputStream(temporary, false)) {
            output.write(text.getBytes(StandardCharsets.UTF_8));
            output.getFD().sync();
        }
        if (destination.exists() && !destination.delete()) {
            throw new IllegalStateException("destination-delete-failed");
        }
        if (!temporary.renameTo(destination)) {
            throw new IllegalStateException("atomic-rename-failed");
        }
    }

    private static String readText(File file) throws Exception {
        if (!file.isFile()) {
            return "";
        }
        byte[] value = new byte[(int) file.length()];
        try (FileInputStream input = new FileInputStream(file)) {
            int offset = 0;
            while (offset < value.length) {
                int read = input.read(value, offset, value.length - offset);
                if (read < 0) {
                    break;
                }
                offset += read;
            }
        }
        return new String(value, StandardCharsets.UTF_8).trim();
    }

    private static Object readJsonOrNull(File file) throws Exception {
        String value = readText(file);
        return value.isEmpty() ? JSONObject.NULL : new JSONObject(value);
    }
}
