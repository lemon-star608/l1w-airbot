# Archived: 3588 slcan module experiment

This note records an out-of-tree module experiment on the 3588 controller
kernel. The current AIRBOT runtime does not use this module: the DISCOVER
USB-CAN adapter is attached to the NX, where the distribution provides the
SLCAN line discipline. Current AIRBOT bring-up is documented in
`../nx-pico-teleop-runbook.md` and `../airbot-bringup.md`.

The working module was moved out of the source tree to:

`/home/lemon/ws-motphys/l1w-airbot-artifacts/kernel/slcan-5.10.160-rt78-preempt-wext.ko`

The SHA-256 below identifies that file.

The L1-W kernel reports `5.10.160-rt78-preempt`, but its ABI differs from a
stock Linux 5.10.160 RT source tree. Two layout differences were observed from
vendor modules:

- `struct module.init` is at offset `0x160`, not stock `0x158`.
- `struct module.exit` is at offset `0x350`, not stock `0x338`.

The first working test module uses `include/linux/module.h` padding fields to
match those offsets. It also enables the hidden vendor setting
`CONFIG_WIRELESS_EXT=y`, which changes `struct net_device`. Without that
setting, `slcand` triggered an oops in `register_netdevice()`.

Working module:

- original repository path: `kernel/slcan-5.10.160-rt78-preempt-wext.ko`
- SHA-256: `2ae99e4f6d07f46e513e0c21f87a4792f05b5e9bb58481cec3c0bded1bc6da6b`
- vermagic: `5.10.160-rt78-preempt SMP preempt_rt mod_unload aarch64`
- `init_module` relocation offset: `0x160`
- `cleanup_module` relocation offset: `0x350`

Verification on L1-W after reboot:

- `insmod` succeeded
- `/proc/tty/ldiscs` contains `slcan 17`
- `slcan@0.service` is active
- `/sys/class/net/can0` exists and is `UP,LOWER_UP`
- a three-second read-only `candump can0` received no frames and reported no
  errors

The first reboot did not make the module persistent by itself: `slcan@0`
failed at boot until the module was manually inserted. The module has now
also been installed for `modprobe`:

```sh
sudo install -m 0644 slcan-wext.ko \
  /lib/modules/$(uname -r)/kernel/drivers/net/can/slcan.ko
sudo depmod -a $(uname -r)
```

`modules.alias` contains `alias tty-ldisc-17 slcan`, so `slcand` can request
the module automatically when it attaches `/dev/ttyCAN0`. A future reboot
should therefore bring up `can0` without a manual `insmod`.

The rejected module without `CONFIG_WIRELESS_EXT` was moved on L1-W to:

`~/ws/kernel-modules/slcan-5.10.160-rt78-preempt.rejected/`

This is still an ABI compatibility experiment, not a vendor-supported module.
The durable fix is to obtain the exact L1-W kernel source or headers and
rebuild all needed modules from that tree.
