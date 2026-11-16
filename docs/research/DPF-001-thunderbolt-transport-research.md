# DPF-001 — Thunderbolt transport follow-up

**Date:** 2026-10-11\
**Target:** M2 Max MacBook Pro ↔ 12.9-inch iPad Pro (6th generation, M2, iPadOS 26.2.1), direct Thunderbolt 3 cable.\
**Decision:** No-go on trying to force direct Thunderbolt or RDMA between these devices. Keep the working USB path; a faster transport experiment is worthwhile only if a measured split-stage bottleneck justifies it.

## What the connection actually is — observed locally

`system_profiler SPUSBHostDataType` lists the iPad as a removable device beneath the Mac's built-in `AppleT8112USBXHCI` **USB 3.1** controller, with **10 Gb/s link speed**. `system_profiler SPThunderboltDataType` lists the Mac's Thunderbolt peripherals, but no iPad. The Mac's `bridge0` Thunderbolt Bridge exists but `ifconfig bridge0` reports **status: inactive**. These are read-only observations on the direct cable, not a 10 Gb/s application-throughput measurement. A bridge interface being present in macOS does not mean this iPad is its peer. No cable, port, or network settings were changed during this follow-up.

Both physical ports are capable of 40 Gb/s in supported modes: Apple rates this [iPad's port](https://support.apple.com/en-us/111841) for Thunderbolt 3 or USB4 up to 40 Gb/s and USB 3 up to 10 Gb/s, and the [M2 Max MacBook Pro's ports](https://support.apple.com/en-us/111838) for Thunderbolt 4 or USB4 up to 40 Gb/s. Those ratings do not identify the protocol negotiated between these two hosts. Here, the iPad enumerates as a **USB device** and the Mac supplies the USB host controller. A different Thunderbolt-rated cable cannot itself cause a different peer service to appear.

The [completed Backburner PoC](DPF-001-ipad-prefill-poc.md) already demonstrated usable application traffic over that USB connection: one large Mac→iPad model transfer was **573 MB in 1.1 s, 525 MB/s** (about 4.2 Gb/s, including app/file work). Its TCP connect plus request/response control round trip had **1.938 ms median** over 30 samples. A 2.5 MiB HTTP/file transfer had **29.036 ms median** over three samples; this is not the split socket's latency. The same PoC measured shorter prefill for one 4B Qwen split, with repeat-run medians of about **20–21%** and one fresh paired prompt at **10%**. None of these is a Thunderbolt measurement.

## Supported software paths and their limits — published documentation

- Apple's [Thunderbolt IP guide](https://support.apple.com/en-tm/guide/mac-help/mchld53dd2f5/mac) describes **two Mac computers** connected by cable and the Thunderbolt Bridge network service. It provides no iPad peer procedure. This establishes a supported Mac-to-Mac path; absence of an iPad procedure alone is not a proof of hardware impossibility.
- Apple's [RDMA over Thunderbolt technote](https://developer.apple.com/documentation/technotes/tn3205-low-latency-communication-with-rdma-over-thunderbolt) states availability beginning with **macOS 26.2 on Apple-silicon Macs with Thunderbolt 5**, for Mac computer clusters. This M2 Max has Thunderbolt 4, and the other endpoint runs iPadOS. The documented RDMA feature therefore cannot be used on this pair. Enabling `rdma_ctl` or building an RDMA client would not remove either requirement.
- iPadOS does support Thunderbolt **accessories**. Apple's [iPadOS DriverKit guide](https://developer.apple.com/documentation/driverkit/creating-drivers-for-ipados) explicitly covers external USB and Thunderbolt devices on M-series iPads, including PCIDriverKit, app packaging, entitlements, and user approval. [PCIDriverKit](https://developer.apple.com/documentation/PCIDriverKit) supports custom PCIe/Thunderbolt peripherals. This is different from a built-in iPad↔Mac Thunderbolt network or RDMA peer mode. A custom two-host bridge would require suitable external endpoint hardware and compatible iPad/Mac drivers or applications; no such hardware is in this setup, and its achievable throughput has not been established.
- [Network.framework](https://developer.apple.com/documentation/network/nwparameters/requiredinterface) can require an interface for sockets. It selects an interface the OS already exposes; it does not negotiate Thunderbolt or create a peer interface. The observed usable interface is the USB link-local network used by Backburner.

**Inference from documentation plus local enumeration:** no supported software switch or ordinary app API was found to turn this direct Mac–iPad connection into a 40 Gb/s Thunderbolt peer. This is a practical no-go for the proposed cable-only PoC, not a claim that iPad Thunderbolt is limited to USB in all uses. Apple's [iPad connection guide](https://support.apple.com/en-us/108894) separately documents Mac synchronization/charging and Thunderbolt display/accessory use, consistent with those distinct roles.

## Bandwidth bound — estimates, not a new benchmark

For the tested Qwen split, one f32 boundary residual is `256 × 2560 × 4 = 2,621,440 bytes = 2.5 MiB`. At the **measured large-file rate** of 525 MB/s, its byte-only serialization time would be **5.0 ms**. At a hypothetical **perfect 40 Gb/s** application rate (5 GB/s), it would be **0.52 ms**. The difference is **4.5 ms per forward residual under those assumptions**. Actual split-socket throughput is unmeasured and could differ from the large-file rate; state synchronization, protocol and scheduling add cost, and 40 Gb/s is a physical rating rather than an application guarantee.

The PoC's iPad eight-layer worker chunks took about **270–299 ms** after the first chunk; later pipeline waits were **0–3 ms** in the main run. These observations do not identify wire time precisely, but they give no evidence that shaving a few milliseconds from the forward residual would materially change this split's prefill result. Return-state traffic and the final state merge could matter more; they need stage-level measurement before transport work. The `2.5 MiB ÷ bandwidth` calculation covers serialization of **one forward tensor only**; it is not a prefill speedup prediction.

## Decision and smallest useful next experiment

**Stop the Thunderbolt/RDMA cable-only branch.** Do not change security settings, install drivers, or build a framework to pursue a peer mode that the OS does not expose. A Thunderbolt dock, adapter, or upgraded cable adds no documented iPad host-to-host service, and RDMA is outside this hardware/platform combination.

If faster communication remains a goal, reuse the provisioned Backburner app and existing model to **time the actual persistent split socket**: boundary send/receive, state push and return, and worker compute for several 2k/4k prompts. Capture latency distributions and total bytes without changing PulsarMLX. Only if the transport share is material should a bounded USB-path optimization be attempted (for example, fewer messages or state-transfer batching, while keeping cable-only access controls). If genuine Thunderbolt accessory hardware later becomes available, first prove that a compatible PCIe endpoint enumerates on the iPad and Mac before any driver work.

This follow-up made no runtime, app, model, network-configuration, or security-setting changes. The note is local and uncommitted.

## Hub connection recheck — 2026-10-11

On the first check after the iPad was moved to a hub, it appeared in neither USB nor Thunderbolt enumeration, and Xcode CoreDevice said `state: disconnected`. The user then allowed the connection in a permission prompt. On recheck, the **Hyper HDTB4PH** appears on a Mac Thunderbolt/USB4 bus at **40 Gb/s upstream**. The iPad appears below a USB 3.0 hub on the Mac's built-in `AppleT8112USBXHCI` controller, with **10 Gb/s link speed**. Both the hub and iPad entries report `USB4 tunnel: Yes`: their USB traffic traverses the USB4 dock connection, while the iPad's exposed USB link remains 10 Gb/s. The iPad does **not** appear as a Thunderbolt peer, and `bridge0` is still **inactive**. Xcode now reports `state: connected`, `transportType: wired`. The permission prompt explains the initial non-enumeration. The earlier direct Mac↔iPad connection also reported 10 Gb/s USB.

## Hyper hub throughput — measured after permission

With the existing Backburner app already responding on the wired link, the existing `phone-push-measure.py` served exactly one local file from the Mac's link-local address and requested the app to fetch it into its Documents directory. The Mac route to the iPad used `en28`; the app reported its cable interface as `en3`. No new app or model was installed. The large test re-fetched the **same 573,295,648-byte tail file** to the existing `tail.gguf` path, so it did not leave an extra large file on the iPad. The small test reused the existing `dpf001-activation-f32.bin` destination.

| Mac→iPad payload | Hub elapsed times | Hub application/file throughput | Earlier direct-cable sample |
| --- | --- | --- | --- |
| 573.296 MB tail | 1.328, 0.907, 0.900, 0.933 s | First **432 MB/s**; three later **632, 637, 614 MB/s**, median **632 MB/s** (~5.1 Gb/s) | One **525 MB/s** transfer |
| 2.5 MiB residual-sized file | 53.579, 28.538, 30.592 ms | Median **30.592 ms** (~85.7 MB/s) | Three samples, median **29.036 ms** |

During the fourth large transfer, `netstat -ibn -I en28` counted **599,428,197 bytes sent** and **1,161,874 bytes received** while the application received the 573,295,648-byte file. This confirms the large payload crossed the wired interface rather than being satisfied solely from the iPad's cache. The transfer includes HTTP, app scheduling, and file writing; it is **one-way Mac→iPad**, not a raw USB or persistent split-socket benchmark. The direct baseline contains only one large-file trial on a different day, so the higher warmed hub rate does **not** establish that the hub is faster. Both topologies negotiated the same 10 Gb/s USB device link. No iPad→Mac bulk throughput was measured.
