# Local Redroid product extension loaded by upstream device/redroid/redroid.mk.
# The host supplies both block devices; game packages remain external.
PRODUCT_COPY_FILES += \
    alas/redroid-native-fbe/fstab.redroid:$(TARGET_COPY_OUT_VENDOR)/etc/fstab.redroid \
    alas/redroid-native-fbe/init.alas-fbe.rc:$(TARGET_COPY_OUT_VENDOR)/etc/init/init.alas-fbe.rc
