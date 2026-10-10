# Native systemd capability experiment

The Codex primary agent produced and verified an isolated systemd experiment on
10 October 2026. Eight actual capability checks and four independent custody
checks passed. This is a service-boundary experiment with synthetic workers,
not a running Gitgood installation or accepted reboot protocol.

## Environment and custody

The source was `Gitgood-Verify-2404` under WSL init. A private root filesystem,
PID/mount/cgroup/network/UTS/IPC namespaces and a unique owned cgroup contained
systemd as PID 1. The verified Ubuntu base archive was 229,623,728 bytes with
SHA-256 `820311e238ea34d76a8ca2643d6c01065212e9417109e7397d70472a236df261`.
Its systemd version was `255.4-1ubuntu8.17`.

The image digest matches the dated
[Ubuntu checksum inventory](https://cloud-images.ubuntu.com/noble/20260926/SHA256SUMS).

The outer experiment was limited to two CPUs and 2 GiB with swap disabled.
The tested service had two CPUs, 256 MiB and no swap. A fixed minimal target
started only the services needed for this capability test. No application,
database, Source credential or Cloud resource was mounted into the fixture.
The private namespace's sysctl tree was read-only in the successful version.

The ordinary service account was UID 65503. Its delegated unit parent carried
the actual `user.delegate` xattr and CPU/memory controllers.
`DelegateSubgroup=driver` placed the manager in its own leaf. The manager
created native/web/edge/maintenance siblings and started actual workers; one
worker created a descendant in a separate process session.

## Observed results

| Check | Actual result |
|---|---|
| Whole-unit stop | All exact worker births and the separate-session descendant stopped. |
| Subsequent start | The same five paths acquired new kernel group inodes. |
| Exact manager SIGKILL | `Restart=on-failure` restarted the unit; prior descendants stopped. |
| Final stop | Every exact manager/worker/descendant was gone or reaped. |
| Persistent custody | Synthetic durable bytes/inode and unit definition bytes/inode were unchanged. |
| Independent post-exit observation | All retained groups in all nine fixtures were empty. |

The three starts observed these inode sequences:

| Group | First | Second | Third |
|---|---|---|---|
| driver | 16584 | 16845 | 17091 |
| native | 16625 | 16886 | 17132 |
| web | 16666 | 16927 | 17173 |
| edge | 16707 | 16968 | 17214 |
| maintenance | 16748 | 17009 | 17255 |

The successful fixture UUID was `cd3e73f0-c1d2-415a-a60b-59d66a530c9d`.
Its private receipt SHA-256 is
`587ab1088462e940559c363717e3852b26f1b159b173efa8b2e65dfe78b3d196`.
The final verifier checked exact old process births, same-path changed inodes,
root-private custody and quiescence. It indexed 835 private diagnostic files;
their contents, filesystem roots and failed attempts remain retained.

A private 16-record producer/metadata archive passed full digest readback.
Its review SHA-256 is
`a7a603487f91266e040e7f29fb97c04e3419148cd9796376b6271d9f7c8990cd`;
its index SHA-256 is
`82b6eb0df5c12d4dacada8bb39b2559c908c6c1daf57b505074d59cece9c808b`.
Four actual executed fixture files match the archived producer. The experiment
executed no native product files; required documentation CI remains a separate
gate.

Eight earlier fresh attempts did not complete the capability proof. Retained
diagnostics exposed a plain chroot lacking a root mount point, archive/device
permission effects from the harness umask, startup bus readiness and an
unavailable pids controller. Separately named fresh versions corrected the
harness. No failed version was relabelled passing.

## Implications and limits

The kernel boot did not change. This proves the selected systemd delegation,
cleanup and restart capabilities; it does not prove artifact readiness,
application writer exclusion, database outage behavior, production service
hardening, real reboot recovery, allocation or Cloud deployment.

The current product's protocol-1 inventory and history remain unchanged.
The [supervision/generation decision](../decisions/0018-native-supervision-generations.md)
specifies the next implementation. Its generation protocol and native controller
still require code and actual installation evidence.

## Separate actual kernel reboot experiment

A subsequent owned VM passed eight capability checks and four independent
custody checks. It ran QEMU 8.2.2 as host UID 1000 inside its exact owned group,
limited to two CPUs and 3 GiB with no swap. The guest had two vCPUs and 2 GiB;
it exposed no network interface or host directory. No global host reboot,
package upgrade, imported WSL distribution or provider operation was used.

The pinned Ubuntu image was 625,612,288 bytes with SHA-256
`6a81c37564db9b1ee84e141922625e1d7c5b389b99bb3c572e0243607d5bb4d2`.
Its digest matched the dated canonical Ubuntu HTTPS checksum inventory; no
detached-signature verification is claimed. Kernel and initrd extraction used
private raw copies and read-only filesystem inspection, with no physical or
loop devices. The original vendor base stayed unchanged.

The guest used kernel `6.8.0-142-generic` and systemd
`255.4-1ubuntu8.17`. Its actual kernel boot changed from
`84f1bc4f-94a9-408f-b684-5812f93502cb` to
`4dcd9c92-b629-41d4-b290-71264dd10583`, while the host boot stayed unchanged.
The ordinary manager automatically started generation 2. Six actual manager,
worker and separate-session descendant births were independently observed on
both boots. Synthetic durable bytes/inode, machine identity and unit
definition bytes/inode were unchanged. All five groups used the same paths;
the new kernel produced new resource identities.

The fixed guest control channel requested only observation, reboot and poweroff.
The VM exited normally after poweroff. Independent post-exit custody verified
all four retained fresh VM fixtures were empty and their private disks and
diagnostics remained intact. The first three attempts failed in the harness
before a complete reboot proof; none was relabelled successful.

The private 21-record source/receipt archive passed digest readback and matched
the original guest seed and Source receipt. Its review SHA-256 is
`36298f6bb6bf59e31cc3756a738632c3a63abbcb5356062c4a7d76ae583c1900`;
its index SHA-256 is
`d54d765672a44e8f29c2f36f40dabdb7a81bfaaf48994f1ee908cef0c56f9361`.

This experiment executed no Gitgood product files or database. It proves the
selected host's reboot capabilities and synthetic persistence. Product service
admission, durable generation continuity, writer exclusion and full lifecycle
recovery require their own source-bound evidence.
