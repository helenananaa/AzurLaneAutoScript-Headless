# KVM on-demand shader candidate

Independent local candidate: `kvm-r75-x86_64-shader-ondemand-20260908-r1`.
The original `kvm-r75-x86_64-local-20260907-r1` release and its default runtime
configuration are retained. This candidate changes one product property:
`PRODUCT_SYSTEM_PROPERTIES += service.sf.prime_shader_cache=false`.

`goldfish.patch` retains the baseline product and other Goldfish changes;
`source-lock.json` pins its bytes, and `profile.json` pins that source lock.
`build-receipt.json` records the J32 incremental build; `release-manifest.json`
records the separately published runtime. No release manifest was edited to
insert a new property after publication.

The retained AOSP source and output now correspond to this candidate. Future
builds of that checkout must use this directory's source lock and profile.
The original source sync receipt remains unchanged: the manifest and project
inventory were reused, with only the Goldfish patch identity advanced.
`source-transition.json` retains the previous source markers.

The candidate runtime config deliberately selects the existing r5 AVD for
controlled same-userdata comparison. Switch its image sysdir using
`manage_kvm_runtime_bundle.py switch-avd` while the service is stopped before
starting this config. Starting without switching is correctly rejected.
Use `rollback-avd` with the original profile and release to restore it.

After selecting the candidate, invoke the Windows manager with both:

```powershell
-Config integration/runtime/kvm-shader-candidate-20260908/runtime-config.json `
-Profile integration/runtime/kvm-shader-candidate-20260908/profile.json
```

Do not re-provision or reset userdata to change the shader setting. Cold-boot
measurements and the final selected runtime are documented in the accompanying
report under `docs`.
