using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Alas.Headless.Contract.Editor
{
    public static class BuildAndroidPlayer
    {
        private const string ScenePath = "Assets/Scenes/ContractBootstrap.unity";
        public static void Build()
        {
            if (Application.unityVersion != "2022.3.62f3")
            {
                throw new InvalidOperationException(
                    "This contract must be built with Unity 2022.3.62f3; found " +
                    Application.unityVersion + ".");
            }

            EnsureBootstrapScene();
            string targetCpu = TargetCpu();
            AndroidArchitecture targetArchitecture = TargetArchitecture(targetCpu);
            string outputPath = targetCpu == "x64"
                ? "Build/HeadlessContract.apk"
                : "Build/HeadlessContract-arm64.apk";
            AndroidArchitecture originalArchitecture =
                PlayerSettings.Android.targetArchitectures;
            try
            {
                ConfigurePlayer(targetArchitecture);

                Directory.CreateDirectory(Path.GetDirectoryName(outputPath) ?? "Build");
                var options = new BuildPlayerOptions
                {
                    scenes = new[] { ScenePath },
                    locationPathName = outputPath,
                    target = BuildTarget.Android,
                    options = BuildOptions.Development
                };
                BuildReport report = BuildPipeline.BuildPlayer(options);
                if (report.summary.result != BuildResult.Succeeded)
                {
                    throw new InvalidOperationException(
                        "Android contract build failed: " + report.summary.result +
                        " errors=" + report.summary.totalErrors);
                }

                Debug.Log("ALAS_UNITY_BUILD " + JsonUtility.ToJson(new BuildEvidence
                {
                    unity = Application.unityVersion,
                    targetCpu = targetCpu,
                    output = Path.GetFullPath(outputPath),
                    bytes = report.summary.totalSize,
                    durationSeconds = report.summary.totalTime.TotalSeconds
                }));
            }
            finally
            {
                PlayerSettings.Android.targetArchitectures = originalArchitecture;
            }
        }

        private static string TargetCpu()
        {
            string value = Environment.GetEnvironmentVariable("ALAS_UNITY_TARGET_CPU");
            if (String.IsNullOrWhiteSpace(value))
            {
                return "x64";
            }
            value = value.Trim().ToLowerInvariant();
            if (value != "x64" && value != "arm64")
            {
                throw new InvalidOperationException(
                    "ALAS_UNITY_TARGET_CPU must be x64 or arm64; found " + value + ".");
            }
            return value;
        }

        private static AndroidArchitecture TargetArchitecture(string targetCpu)
        {
            return targetCpu == "arm64"
                ? AndroidArchitecture.ARM64
                : AndroidArchitecture.X86_64;
        }

        private static void EnsureBootstrapScene()
        {
            if (File.Exists(ScenePath))
            {
                Scene existing = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
                GameObject existingMarker = GameObject.Find("ContractBootstrapMarker");
                if (!existing.IsValid() || existingMarker == null ||
                    existingMarker.GetComponent<SemanticMarker>() == null)
                {
                    throw new InvalidOperationException(
                        "Existing bootstrap scene does not contain the semantic marker.");
                }
                EditorBuildSettings.scenes = new[]
                {
                    new EditorBuildSettingsScene(ScenePath, true)
                };
                return;
            }

            Directory.CreateDirectory("Assets/Scenes");
            Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var marker = new GameObject("ContractBootstrapMarker");
            marker.AddComponent<SemanticMarker>().Initialize("contract/bootstrap");
            if (!EditorSceneManager.SaveScene(scene, ScenePath))
            {
                throw new InvalidOperationException("Unable to save " + ScenePath);
            }
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
        }

        private static void ConfigurePlayer(AndroidArchitecture targetArchitecture)
        {
            if (!EditorUserBuildSettings.SwitchActiveBuildTarget(
                    BuildTargetGroup.Android, BuildTarget.Android))
            {
                throw new InvalidOperationException("Unable to switch the active target to Android.");
            }

            PlayerSettings.companyName = "ALAS Headless Research";
            PlayerSettings.productName = "ALAS Headless Contract";
            PlayerSettings.bundleVersion = "0.1.0";
            PlayerSettings.SetApplicationIdentifier(
                BuildTargetGroup.Android, "io.github.alasheadless.unitycontract");
            PlayerSettings.SetScriptingBackend(
                BuildTargetGroup.Android, ScriptingImplementation.IL2CPP);
            PlayerSettings.Android.targetArchitectures = targetArchitecture;
            PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel29;
            PlayerSettings.Android.targetSdkVersion = AndroidSdkVersions.AndroidApiLevelAuto;
            PlayerSettings.Android.bundleVersionCode = 1;
            PlayerSettings.defaultInterfaceOrientation = UIOrientation.LandscapeLeft;
            EditorUserBuildSettings.buildAppBundle = false;
        }

        [Serializable]
        private sealed class BuildEvidence
        {
            public string unity;
            public string targetCpu;
            public string output;
            public ulong bytes;
            public double durationSeconds;
        }
    }
}
