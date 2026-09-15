"""Glossary content (WP15) — pure Python, no GTK.

Roughly a hundred short, checkable entries covering Linux disks, partitions,
filesystems, mounting, space accounting, the directory tree, storage
subsystems, and best practices. ``GlossaryPage`` (``ui/pages/glossary.py``)
is the only consumer today; ``get()`` is meant to be reused later by
tooltips/links elsewhere in the app.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Term:
    """One glossary entry."""

    key: str
    title: str
    category: str
    summary: str
    body: str
    related: tuple[str, ...] = ()


CATEGORIES: tuple[tuple[str, str], ...] = (
    ("disks", "Disks & Partitions"),
    ("filesystems", "Filesystems"),
    ("mounting", "Mounting"),
    ("space", "Space & Sizes"),
    ("directories", "Directories & the Tree"),
    ("subsystems", "Storage Subsystems"),
    ("practices", "Best Practices"),
)

# ---- Disks & Partitions -----------------------------------------------------

_DISKS: tuple[Term, ...] = (
    Term(
        "block-device",
        "Block Device",
        "disks",
        "A device the kernel accesses in fixed-size chunks (blocks), such as a disk or partition.",
        "A block device is anything the kernel can read and write in fixed-size blocks rather "
        "than a continuous stream, which is what character devices do. Disks, partitions, RAID "
        "arrays, and LVM logical volumes all show up as block devices under /dev. Utilities like "
        "lsblk, fdisk, and df operate on block devices, and every filesystem is built on top of "
        "one.",
        ("lsblk", "partition-table"),
    ),
    Term(
        "disk-vs-partition",
        "Disk vs. Partition",
        "disks",
        "A disk is the whole physical (or virtual) drive; a partition is a labelled slice of it.",
        "A disk, such as /dev/sda or /dev/nvme0n1, is the entire storage device as the kernel "
        "sees it. A partition, such as /dev/sda1, is a defined region of that disk described in "
        "a partition table, and each partition can hold its own filesystem, swap area, or be "
        "left unformatted. A single disk commonly holds several partitions, for example one for "
        "the EFI System Partition, one for the root filesystem, and one for swap.",
        ("partition-table", "device-names"),
    ),
    Term(
        "device-names",
        "Device Names",
        "disks",
        "How Linux names disks and partitions under /dev: sda1, nvme0n1p2, mmcblk0p1, dm-0, loop0.",
        "SATA/USB/SCSI disks appear as /dev/sda, /dev/sdb, and so on, with partitions numbered "
        "afterwards (/dev/sda1). NVMe drives use /dev/nvme0n1, with a 'p' before the partition "
        "number (/dev/nvme0n1p2) because the base name already ends in a digit. SD/MMC cards use "
        "/dev/mmcblk0 the same way (/dev/mmcblk0p1). Device-mapper targets, such as LVM volumes "
        "or LUKS containers, appear as /dev/dm-0 (or a friendlier symlink under /dev/mapper/), "
        "and loopback-mounted disk images appear as /dev/loop0. These names can be reassigned on "
        "reboot, which is why fstab entries should prefer a UUID or label.",
        ("uuid", "lvm", "luks-dmcrypt"),
    ),
    Term(
        "partition-table",
        "Partition Table (MBR vs. GPT)",
        "disks",
        "The on-disk index of partitions; the older MBR scheme or the modern GPT scheme.",
        "A partition table lives in the first sectors of a disk and records where each partition "
        "starts, how big it is, and what type it is. MBR (Master Boot Record), the legacy "
        "DOS-era scheme, supports at most four primary partitions and disks up to 2 TiB. GPT "
        "(GUID Partition Table) replaced it: it supports up to 128 partitions by default, disks "
        "far larger than 2 TiB, stores a backup copy at the end of the disk, and is required for "
        "UEFI booting. New disks should use GPT unless something specifically needs MBR.",
        ("efi-system-partition", "gpt-for-new-disks"),
    ),
    Term(
        "efi-system-partition",
        "EFI System Partition (ESP)",
        "disks",
        "A small FAT32 partition that holds the bootloader files a UEFI firmware reads directly.",
        "The EFI System Partition is a FAT32-formatted partition, typically 100 to 500 MiB, that "
        "a UEFI firmware can read without any OS driver. It stores bootloaders and boot managers "
        "(for example /EFI/ubuntu/grubx64.efi) as plain files. On Linux it is usually mounted at "
        "/boot/efi. It is unrelated to swap or to the root filesystem and should never be "
        "deleted or resized casually -- doing so can leave a machine unable to boot.",
        ("gpt-for-new-disks", "boot-directory"),
    ),
    Term(
        "sector",
        "Sector",
        "disks",
        "The smallest unit a disk transfers in one operation, traditionally 512 bytes, now "
        "often 4096.",
        "A sector is the disk's native read/write unit. Older disks used 512-byte sectors; most "
        "modern HDDs and SSDs use 4096-byte ('4Kn' or '512e' emulated) sectors internally for "
        "efficiency. Filesystems and partition tools build on top of sectors, and misaligned "
        "partitions that straddle sector or SSD erase-block boundaries can hurt performance.",
        ("alignment", "lba"),
    ),
    Term(
        "lba",
        "LBA (Logical Block Addressing)",
        "disks",
        "The scheme that numbers every sector on a disk 0, 1, 2, ... instead of old cylinder/"
        "head/sector geometry.",
        "LBA gives every addressable block on a disk a single sequential number, which is what "
        "the kernel, partition tables, and filesystems actually use to read or write. It "
        "replaced the older CHS (cylinder-head-sector) addressing that mattered on very old "
        "hardware. Partition start/end offsets you see in fdisk or parted are LBA numbers.",
        ("sector", "partition-table"),
    ),
    Term(
        "alignment",
        "Partition Alignment",
        "disks",
        "Starting a partition on a boundary that matches the disk's physical block size, to "
        "avoid slow read-modify-write cycles.",
        "When a partition's start offset doesn't line up with the disk's physical sector or "
        "SSD erase-block size, a single logical write can force the drive to read, modify, and "
        "rewrite two physical blocks instead of one, hurting throughput and, on SSDs, wear. "
        "Modern partitioning tools (parted, gdisk, GNOME Disks) align new partitions to 1 MiB "
        "by default, which is safe for virtually all current hardware. Misalignment mostly "
        "bites disks partitioned long ago or moved between very different drive geometries.",
        ("sector", "ssd-vs-hdd-vs-nvme"),
    ),
    Term(
        "ssd-vs-hdd-vs-nvme",
        "SSD vs. HDD vs. NVMe",
        "disks",
        "Three drive types with very different performance characteristics, all exposed to "
        "Linux as ordinary block devices.",
        "An HDD (hard disk drive) stores data magnetically on spinning platters; it's cheap per "
        "gigabyte but slow for random access because of seek time. An SSD (solid-state drive) "
        "stores data in flash memory with no moving parts, giving much faster random I/O; most "
        "connect over SATA. NVMe drives are flash storage connected directly over PCIe using a "
        "protocol designed for it, giving far higher throughput and much lower latency than "
        "SATA SSDs, and they use deep command queues that suit modern multi-core systems. "
        "LinDriveSpace reports space usage the same way regardless of drive type; only "
        "underlying speed differs.",
        ("trim", "nvme-queues", "sata-ahci"),
    ),
    Term(
        "trim",
        "TRIM / discard",
        "disks",
        "A command that tells an SSD which blocks no longer hold live data, so it can erase "
        "them ahead of time.",
        "Unlike an HDD, an SSD can't overwrite a block in place -- it must erase a whole block "
        "before rewriting it. TRIM (the ATA command; 'discard' or 'UNMAP' on other interfaces) "
        "lets the filesystem tell the drive 'these blocks are free now,' so the SSD's controller "
        "can erase them in the background instead of scrambling during a future write. Linux "
        "can send TRIM continuously via the discard mount option, or periodically via the "
        "fstrim.timer service, usually the preferred approach since continuous discard can add "
        "latency.",
        ("wear-levelling", "trim-weekly"),
    ),
    Term(
        "wear-levelling",
        "Wear Levelling",
        "disks",
        "How an SSD controller spreads writes evenly across flash cells so no one cell wears "
        "out first.",
        "Flash memory cells can only be erased and rewritten a limited number of times before "
        "they degrade. An SSD's controller transparently remaps logical addresses to physical "
        "cells and rotates writes across the whole chip (wear levelling) so that no single cell "
        "is hammered while others sit idle. This, plus TRIM and a spare-cell pool "
        "(over-provisioning), is why SSDs last for years of normal desktop use despite the "
        "underlying flash's finite endurance.",
        ("trim", "smart"),
    ),
    Term(
        "smart",
        "SMART",
        "disks",
        "Self-Monitoring, Analysis and Reporting Technology -- a drive's built-in health and "
        "error-counter reporting.",
        "SMART is a set of attributes a disk's own firmware tracks and reports, covering things "
        "like reallocated sectors, power-on hours, temperature, and (on SSDs) remaining write "
        "endurance. Tools like smartctl (package smartmontools) can read these attributes and "
        "run self-tests. A rising reallocated-sector count or a failed self-test is an early "
        "warning a drive is failing, well before a filesystem error appears.",
        ("wear-levelling", "monitor-smart-practice"),
    ),
    Term(
        "hotplug-udev",
        "Hot-Plug & udev",
        "disks",
        "How Linux notices a disk (USB stick, SD card) as soon as it's connected, without a "
        "reboot.",
        "When a storage device is plugged in, the kernel detects it and emits a 'uevent'; the "
        "udev daemon (systemd-udevd) picks that up, creates the /dev device node, and runs any "
        "matching rules -- for example, assigning a stable /dev/disk/by-id symlink or "
        "triggering an automount under /media/$USER. This is what lets a desktop show a "
        "notification and mount a USB drive automatically, no manual mount command needed.",
        ("udev", "automount", "removable-media"),
    ),
)

# ---- Filesystems -------------------------------------------------------------

_FILESYSTEMS: tuple[Term, ...] = (
    Term(
        "ext-meaning",
        'What "ext" Means',
        "filesystems",
        "ext = extended filesystem: the Linux-native filesystem family, first released in 1992.",
        'ext stands for "extended filesystem." It was written for Linux in 1992 as an '
        "improvement on the Minix filesystem the earliest Linux kernels used. Its descendants "
        "-- ext2, ext3, and ext4 -- have been the default root filesystem on most Linux "
        "distributions for decades, including most Linux Mint installs.",
        ("ext2", "ext3", "ext4"),
    ),
    Term(
        "ext2",
        "ext2",
        "filesystems",
        "The second extended filesystem (1993): fast, simple, and without a journal.",
        "ext2 was the first widely used ext filesystem. It has no journal, so after an unclean "
        "shutdown it needs a full fsck pass to check consistency, which can take a long time on "
        "a large volume. Because it writes no journal, it causes slightly less wear on flash "
        "storage, which is why it's still sometimes chosen for small /boot partitions today.",
        ("ext3", "fsck", "journaling"),
    ),
    Term(
        "ext3",
        "ext3",
        "filesystems",
        "ext2 plus journaling (2001): the same on-disk layout, with a log that makes crash "
        "recovery fast.",
        "ext3 added a journal to ext2's layout: before changing metadata, the filesystem first "
        "writes a short description of the change to a log. After an unclean shutdown, it "
        "replays that log instead of scanning the whole volume, so recovery takes seconds "
        "rather than minutes or hours. It was designed to be mountable as ext2 and vice versa, "
        "which made upgrading painless.",
        ("ext2", "ext4", "journaling"),
    ),
    Term(
        "ext4",
        "ext4",
        "filesystems",
        "The current default ext filesystem (2008): extents, delayed allocation, huge volume/"
        "file limits, a journal.",
        "ext4 extended ext3 with extents -- a way of describing a large run of contiguous "
        "blocks with one record instead of one entry per block -- which makes large files "
        "faster to map and less fragmented. It adds delayed allocation (deferring block "
        "placement until data is actually flushed, for better layout decisions), "
        "nanosecond-resolution timestamps, and much higher limits: up to 1 EiB volumes and "
        "16 TiB individual files. Like ext3, it keeps a journal for fast crash recovery, and "
        "its journal can be checksummed for extra safety. It's the default root filesystem on "
        "most current Linux Mint and Ubuntu installs.",
        ("ext3", "journaling", "inode"),
    ),
    Term(
        "journaling",
        "Journaling",
        "filesystems",
        "Writing a short log of pending metadata changes before applying them, so a crash can "
        "be recovered from quickly.",
        "A journaling filesystem writes a compact record of an upcoming metadata change to a "
        "reserved log area before it modifies the real structures on disk. If the system "
        "crashes mid-write, the filesystem replays the journal on next mount to finish or roll "
        "back the interrupted operation, avoiding a lengthy full-volume check. ext3, ext4, "
        "XFS, and Btrfs all journal (Btrfs uses a similar copy-on-write log rather than a "
        "classic journal); ext2 and FAT do not.",
        ("ext3", "ext4", "xfs", "fsck"),
    ),
    Term(
        "xfs",
        "XFS",
        "filesystems",
        "A high-performance journaling filesystem, strong on large files and parallel I/O; "
        "RHEL/CentOS's default.",
        "XFS was originally developed by SGI and is now a mainline Linux filesystem, tuned for "
        "large files, high-throughput and highly parallel I/O. It journals metadata for fast "
        "crash recovery and supports very large volumes. It's less commonly the default on "
        "Ubuntu/Mint (which favour ext4) but is a solid choice for data-heavy servers and can "
        "be used as a secondary drive's filesystem on any distro.",
        ("journaling", "ext4"),
    ),
    Term(
        "btrfs",
        "Btrfs",
        "filesystems",
        "A copy-on-write filesystem with built-in snapshots, subvolumes, and compression.",
        "Btrfs ('B-tree filesystem') never overwrites data in place -- it writes changes to new "
        "blocks and atomically updates pointers, which is what makes cheap, instant snapshots "
        "possible. It supports subvolumes (independently mountable/snapshottable trees within "
        "one filesystem), transparent compression, and built-in RAID-like multi-device "
        "profiles. Because of copy-on-write and snapshots, du can report far less space than "
        "the filesystem actually has allocated for a file, since old snapshotted blocks are "
        "still referenced -- a common source of confusion when comparing tools like "
        "LinDriveSpace against df.",
        ("snapshots-practice", "reflinks", "zfs"),
    ),
    Term(
        "zfs",
        "ZFS",
        "filesystems",
        "A copy-on-write filesystem and volume manager combined, with checksummed data, "
        "snapshots, and pooled storage.",
        "ZFS merges the roles of filesystem and volume manager: you give it raw disks, and it "
        "manages pooling, RAID-like redundancy, snapshots, and per-block checksums that let it "
        "detect and, with redundancy, repair silent data corruption. On Linux it ships as an "
        "out-of-tree module (OpenZFS) rather than being mainlined, due to licensing, so it "
        "needs separate installation (e.g. via zfsutils-linux) rather than being built into the "
        "kernel like ext4.",
        ("btrfs", "lvm"),
    ),
    Term(
        "f2fs",
        "F2FS",
        "filesystems",
        "The Flash-Friendly File System, designed around how NAND flash actually erases and "
        "writes data.",
        "F2FS was designed by Samsung specifically for NAND flash storage (SSDs, eMMC, SD "
        "cards), using a log-structured layout that matches flash's erase-before-write "
        "behaviour to reduce write amplification and improve performance and lifespan. It's "
        "commonly used on Android and on single-board computers with eMMC/SD storage; it's "
        "less common as a Linux Mint desktop root filesystem but a reasonable choice for small "
        "flash-based systems.",
        ("trim", "ext4"),
    ),
    Term(
        "vfat-exfat-ntfs",
        "vfat, exFAT, NTFS",
        "filesystems",
        "Non-Linux filesystems kept around chiefly for interoperability with Windows, cameras, "
        "and USB drives.",
        "vfat (FAT32 with long filenames) is the lowest-common-denominator filesystem most USB "
        "sticks, SD cards, and camera media ship formatted with, but it caps individual files "
        "at 4 GiB. exFAT removes that limit and is common on larger flash drives and SD cards "
        "while staying readable on Windows and macOS. NTFS is Windows' native filesystem, "
        "readable and writable on Linux via the ntfs3 kernel driver or the older FUSE-based "
        "ntfs-3g. None of the three support Linux permissions/ownership natively, so files on "
        "them typically show fixed, mount-option-controlled permissions.",
        ("fuse", "mount-options"),
    ),
    Term(
        "squashfs",
        "SquashFS",
        "filesystems",
        "A read-only, compressed filesystem used to pack a whole tree of files into one image "
        "-- the basis of Snap packages and live/installer media.",
        "SquashFS compresses a directory tree into a single read-only image file, which is "
        "mounted (often via a loop device) rather than written to directly. It underlies Snap "
        "packages (each revision is a .snap SquashFS image mounted read-only), live-CD/USB "
        "Linux images, and some container layers. Because it's read-only and compressed, it's "
        "efficient for distributing fixed content but not used for a working root filesystem.",
        ("loop-mounts", "package-caches"),
    ),
    Term(
        "tmpfs",
        "tmpfs",
        "filesystems",
        "A filesystem backed by RAM (and swap, if needed): fast, but its contents vanish on "
        "reboot.",
        "tmpfs stores its files in kernel memory rather than on disk, so reads and writes are "
        "essentially RAM-speed, but everything in it is lost at unmount or reboot. Linux mounts "
        "/run, /dev/shm, and often /tmp as tmpfs by default. Because it counts against RAM (and "
        "can spill into swap), a runaway process writing to a tmpfs mount can exhaust memory "
        "the same way a memory leak would.",
        ("tmp-directory", "swap"),
    ),
    Term(
        "overlayfs",
        "OverlayFS",
        "filesystems",
        "A filesystem that layers a writable directory on top of one or more read-only ones -- "
        "the mechanism behind Docker images and many live-USB systems.",
        "OverlayFS combines a read-only 'lower' directory with a writable 'upper' directory "
        "into a single merged view: reads fall through to the lower layer when a file hasn't "
        "been changed, and any write is copied up to the upper layer first (copy-on-write at "
        "the file level). This is exactly how container images share a common read-only base "
        "while giving each container its own writable layer, and it's also how many live-USB "
        "Linux sessions let you 'modify' a read-only squashfs image during the session.",
        ("squashfs", "fuse"),
    ),
    Term(
        "fuse",
        "FUSE",
        "filesystems",
        "Filesystem in Userspace -- lets an ordinary program implement a filesystem without "
        "kernel code.",
        "FUSE is a kernel module plus library that lets a regular user-space program handle "
        "filesystem calls (open, read, write, readdir...) instead of requiring a kernel driver. "
        "It's what makes sshfs (mounting a remote directory over SSH), ntfs-3g, and "
        "GVFS-backed mounts (like a phone or a cloud-drive folder shown in Nautilus) possible "
        "without writing kernel code. FUSE filesystems are generally slower than native "
        "in-kernel ones because every call round-trips to a user-space process.",
        ("network-mounts", "vfat-exfat-ntfs"),
    ),
    Term(
        "pseudo-filesystems",
        "Pseudo Filesystems (/proc, /sys, /dev)",
        "filesystems",
        "Filesystems that don't store files at all -- they present live kernel data as a "
        "directory tree.",
        "/proc (procfs) exposes running processes and kernel state as virtual files, e.g. "
        "/proc/meminfo or /proc/self/mountinfo. /sys (sysfs) exposes the kernel's device and "
        "driver model, used to query or tune hardware. /dev, when mounted as devtmpfs, holds "
        "device nodes the kernel creates automatically as hardware is detected. None of these "
        "use real disk space for their 'files' -- their reported sizes are nominal or zero, "
        "and they should never be treated as ordinary directories to scan, back up, or delete "
        "from.",
        ("proc-directory", "sys-directory", "dev-directory", "dont-delete-pseudo-fs"),
    ),
    Term(
        "inode",
        "Inode",
        "filesystems",
        "The metadata record for one file: owner, permissions, size, timestamps, and pointers "
        "to its data blocks -- everything except the name.",
        "Every file on a Unix-style filesystem has an inode holding its metadata and the "
        "addresses of the blocks (or, on ext4, the extents) that hold its actual data. A "
        "directory entry is just a name mapped to an inode number; that's why a hard link can "
        "give a file two names sharing one inode, and why renaming a file is cheap (only the "
        "directory entry changes, not the inode). A filesystem has a fixed number of inodes "
        "decided at format time, so it's possible to run out of inodes (df -i) while blocks of "
        "free space remain, typically from millions of tiny files.",
        ("hard-links", "superblock", "df"),
    ),
    Term(
        "superblock",
        "Superblock",
        "filesystems",
        "The filesystem's own header record: its type, size, block size, and where to find "
        "everything else.",
        "The superblock is a small structure near the start of a filesystem that records its "
        "type, total size, block size, and the locations of core structures like the inode "
        "table and free-space bitmaps. ext-family filesystems keep backup copies of the "
        "superblock scattered through the volume so a damaged primary copy can be recovered. "
        "Tools like mkfs, fsck, and tune2fs read and, in some cases, rewrite it.",
        ("mkfs", "fsck", "block-size"),
    ),
    Term(
        "block-size",
        "Block Size",
        "filesystems",
        "The smallest chunk of space a filesystem allocates to a file, commonly 4 KiB on ext4.",
        "A filesystem doesn't hand out space one byte at a time -- it allocates in fixed-size "
        "blocks, most often 4 KiB on ext4 and similar filesystems. A 10-byte file still "
        "consumes one whole block on disk; this is why du (allocated size, block-aligned) is "
        "usually larger than a small file's ls -l byte count, even though for large files the "
        "difference becomes negligible.",
        ("apparent-vs-allocated-size", "superblock"),
    ),
    Term(
        "reserved-blocks",
        "Reserved Blocks (root reserve)",
        "filesystems",
        "A slice of an ext filesystem -- 5% by default -- held back so only root can use it "
        "once the volume looks full.",
        "ext2/3/4 filesystems reserve a percentage of total space (5% by default, set at "
        "format time or later with tune2fs -m) that only the root user can allocate into. This "
        "exists so that, even when a filesystem looks completely full to ordinary users, "
        "root-owned services (logging, system daemons) can still write enough to let an "
        "administrator fix the problem. It's why df for a nearly-full ext4 volume can show a "
        "small amount of 'used' space beyond what any user-visible file accounts for, and why "
        "lowering the reserve is sometimes done on large data-only ext4 volumes to reclaim "
        "usable space.",
        ("ext4", "df"),
    ),
    Term(
        "fsck",
        "fsck",
        "filesystems",
        "The filesystem consistency checker -- verifies and, where possible, repairs a "
        "filesystem's internal structures.",
        "fsck (filesystem check) walks a filesystem's metadata -- inodes, directory entries, "
        "free-space maps -- looking for inconsistencies, such as blocks marked used but "
        "referenced by nothing, and fixes what it can. It normally runs automatically on an "
        "unclean shutdown or after a scheduled interval; a journaling filesystem (ext3/4, XFS) "
        "needs it far less often, and only for real corruption, since the journal already "
        "covers normal crash recovery. fsck should never run against a mounted, in-use "
        "filesystem.",
        ("journaling", "superblock"),
    ),
    Term(
        "mkfs",
        "mkfs",
        "filesystems",
        "The command family that formats a partition or device with a filesystem (mkfs.ext4, "
        "mkfs.xfs, mkfs.vfat, ...).",
        "mkfs (make filesystem) writes a fresh, empty filesystem structure -- a superblock, "
        "inode table, free-space maps -- onto a block device, erasing whatever was there "
        "before. Each filesystem type has its own variant, e.g. mkfs.ext4 /dev/sdb1 or "
        "mkfs.vfat -F32 /dev/sdc1. It's a destructive operation and should only ever target "
        "the intended partition, never a whole disk that still holds other partitions you want "
        "to keep.",
        ("partition-table", "label"),
    ),
    Term(
        "label",
        "Filesystem Label",
        "filesystems",
        "A short, human-chosen name stamped into a filesystem, usable in /etc/fstab instead of "
        "a device path.",
        "A label is an optional short name set at format time (or later, with e.g. e2label) "
        "and stored inside the filesystem itself. Labelling a partition 'DATA' or 'BACKUP' "
        "makes it easy to identify in a file manager or in /etc/fstab (LABEL=DATA), and unlike "
        "a /dev/sdXN name it doesn't change if drives are reordered -- though a UUID is still "
        "the more reliable identifier since labels aren't guaranteed unique.",
        ("uuid", "fstab"),
    ),
    Term(
        "uuid",
        "UUID",
        "filesystems",
        "A universally unique identifier generated for a filesystem at format time; the "
        "recommended way to reference it in fstab.",
        "A UUID (Universally Unique Identifier) is a long, effectively-unique string assigned "
        "to a filesystem when it's created. Because it travels with the filesystem regardless "
        "of which /dev/sdXN name the kernel happens to assign it this boot, /etc/fstab entries "
        "and bootloader configs typically reference partitions by UUID rather than by device "
        "name, so the system still boots correctly after a drive is added, removed, or "
        "reordered. blkid and lsblk -f show a device's UUID.",
        ("label", "fstab", "device-names"),
    ),
    Term(
        "fstab",
        "/etc/fstab",
        "filesystems",
        "The system's table of filesystems to mount at boot, and how -- what device, what "
        "mountpoint, what options.",
        "/etc/fstab lists, one line per entry, what to mount (by UUID, label, or device path), "
        "where to mount it (the mountpoint), what filesystem type it is, and which mount "
        "options to use, plus dump/fsck-order flags. systemd generates mount units from it at "
        "boot. A typo, or a missing device referenced with the old hard 'must mount' behaviour, "
        "can drop a system to an emergency shell, which is why editing it calls for care (and "
        "why 'nofail' is often added for removable or optional drives).",
        ("mount-options", "uuid", "systemd-mount-units"),
    ),
)

# ---- Mounting ------------------------------------------------------------

_MOUNTING: tuple[Term, ...] = (
    Term(
        "mount",
        "Mount",
        "mounting",
        "Attaching a filesystem to the directory tree so its contents become visible at a path.",
        "Mounting makes a filesystem's contents appear under a chosen directory (the "
        "mountpoint) rather than requiring it to be addressed by device name. Until mounted, a "
        "partition's files are inaccessible through the normal path-based filesystem "
        "interface. The mount command does this manually; /etc/fstab and systemd mount units "
        "do it automatically at boot; desktop environments do it automatically for removable "
        "media.",
        ("mountpoint", "unmount", "fstab"),
    ),
    Term(
        "mountpoint",
        "Mountpoint",
        "mounting",
        "The directory a filesystem is attached to; everything under it belongs to that "
        "filesystem until unmounted.",
        "A mountpoint is an ordinary directory that a filesystem gets attached to. When a "
        "separate partition is mounted at /home, for example, the /home directory momentarily "
        "'becomes' the root of that partition's file tree, and anything that used to be in "
        "that directory before the mount is hidden until it's unmounted again. This is why a "
        "system can have '/' on one partition and '/home' on another, each with its own free "
        "space, and why df reports usage per mountpoint rather than per directory.",
        ("mount", "root-directory", "home-directory", "findmnt"),
    ),
    Term(
        "unmount",
        "Unmount",
        "mounting",
        "Detaching a filesystem from its mountpoint, making its contents inaccessible until "
        "it's mounted again.",
        "Unmounting (umount) detaches a filesystem from its mountpoint and flushes any pending "
        "writes to it. It fails with 'device is busy' if a process still has an open file or a "
        "shell has its working directory inside the mount -- lsof or fuser can identify the "
        "culprit. Removable media should always be unmounted (or 'safely removed') before "
        "physical disconnection to avoid losing unflushed writes.",
        ("mount", "removable-media"),
    ),
    Term(
        "mount-options",
        "Mount Options",
        "mounting",
        "Flags set at mount time that change a filesystem's behaviour: noatime, relatime, "
        "discard, ro, and more.",
        "Mount options tune how a filesystem behaves without changing the data on it. noatime "
        "skips updating a file's last-accessed time on every read, reducing write traffic; "
        "relatime (the modern default) is a lighter compromise that still updates atime "
        "occasionally. discard sends TRIM continuously as blocks free up; ro mounts read-only; "
        "defaults picks the usual set for the filesystem type; and desktop-integration options "
        "like x-gvfs-show tell the file manager to display a mount in its sidebar. Options are "
        "set per mount, in /etc/fstab or on the mount command line.",
        ("fstab", "noatime-practice", "trim"),
    ),
    Term(
        "bind-mount",
        "Bind Mount",
        "mounting",
        "Mounting one directory at a second location, so both paths show the same underlying "
        "files.",
        "A bind mount (mount --bind /source /target) doesn't attach a new filesystem -- it "
        "makes an already-mounted directory also appear at another path, with both locations "
        "reading and writing the exact same files. It's commonly used to expose part of the "
        "host filesystem inside a chroot or container, or to relocate a directory (like moving "
        "/var/log to a bigger disk) while keeping the original path working.",
        ("mount", "overlayfs"),
    ),
    Term(
        "automount",
        "Automount",
        "mounting",
        "Mounting a filesystem automatically, either on access (systemd/autofs) or on device "
        "insertion (desktop udisks).",
        "Automount covers two related things: on-demand mounting, where a path is only "
        "actually mounted the moment something accesses it (systemd .automount units, or the "
        "older autofs), which is common for network shares; and removable-media "
        "automounting, where inserting a USB drive or SD card triggers udisks2 to mount it "
        "under /media/$USER without any user action. Both save you from mounting things by "
        "hand.",
        ("hotplug-udev", "removable-media", "systemd-mount-units"),
    ),
    Term(
        "mountinfo",
        "/proc/self/mountinfo",
        "mounting",
        "The kernel's live, authoritative list of every current mount, its options, and its "
        "mount ID.",
        "/proc/self/mountinfo (and /proc/<pid>/mountinfo for other processes) is a virtual "
        "file listing every filesystem currently mounted as that process sees it, including "
        "mount and parent IDs, the mountpoint, filesystem type, and effective mount options. "
        "It's more complete and more reliable to parse than the older /etc/mtab, and it's what "
        "tools like findmnt read under the hood.",
        ("findmnt", "pseudo-filesystems"),
    ),
    Term(
        "findmnt",
        "findmnt",
        "mounting",
        "A command that lists and searches current mounts in a readable tree, reading "
        "/proc/self/mountinfo.",
        "findmnt shows currently mounted filesystems, their mountpoints, types, and options, "
        "and can render them as a tree that reflects nested mounts. It's useful for checking "
        "exactly which options a mount ended up with (which can differ from what fstab "
        "requested, if the filesystem doesn't support one of them), or for confirming whether "
        "a given path is itself a mountpoint (findmnt /path).",
        ("mountinfo", "lsblk"),
    ),
    Term(
        "lsblk",
        "lsblk",
        "mounting",
        "Lists block devices as a tree -- disks, their partitions, and what (if anything) each "
        "is mounted on.",
        "lsblk prints every block device the kernel knows about -- disks, partitions, LVM "
        "volumes, loop devices -- as a tree, showing size, type, and current mountpoint for "
        "each. lsblk -f adds filesystem type, label, and UUID. It's usually the fastest way to "
        "answer 'what drives and partitions does this machine actually have, and where are "
        "they mounted.'",
        ("device-names", "findmnt"),
    ),
    Term(
        "df",
        "df",
        "mounting",
        "Reports free/used/total space per mounted filesystem -- the numbers behind "
        "LinDriveSpace's Overview page.",
        "df (disk free) reports, per mounted filesystem, its total size, space used, space "
        "available, and percentage full, as tracked by the filesystem itself. df -h prints "
        "human-readable sizes. Because it works per mountpoint rather than per directory, "
        "df /home and df / can report completely different totals if they're separate "
        "partitions -- and df's notion of 'used' includes filesystem overhead and reserved "
        "blocks that a simple sum of visible file sizes wouldn't.",
        ("du", "used-free-total", "mountpoint"),
    ),
    Term(
        "du",
        "du",
        "mounting",
        "Reports how much disk space a directory tree actually consumes, walking every file "
        "underneath it.",
        "du (disk usage) walks a directory recursively and sums the allocated size of every "
        "file it finds, unlike df which reports a whole filesystem's status from its own "
        "accounting. du -sh gives one human-readable total for a folder. By default du reports "
        "allocated space (blocks actually reserved on disk), which is usually somewhat larger "
        "than the sum of files' apparent byte sizes, and can be dramatically different from it "
        "on a filesystem using compression or copy-on-write like Btrfs or ZFS.",
        ("df", "apparent-vs-allocated-size", "ncdu"),
    ),
    Term(
        "ncdu",
        "ncdu",
        "mounting",
        "An interactive, terminal-based disk-usage browser -- a lightweight ancestor of what "
        "LinDriveSpace does graphically.",
        "ncdu (NCurses Disk Usage) scans a directory tree and lets you interactively browse it "
        "sorted by size, drilling into subfolders and deleting files directly from the "
        "interface. It's a common quick, dependency-free way to find what's eating space on a "
        "headless server; LinDriveSpace covers the same job with a full GTK GUI, treemap, and "
        "per-mount overview.",
        ("du", "percent-of-parent"),
    ),
    Term(
        "systemd-mount-units",
        "systemd Mount Units",
        "mounting",
        "systemd's own representation of a mount (name.mount) and on-demand mount "
        "(name.automount), generated from fstab or written by hand.",
        "systemd represents each mount as a .mount unit (for example home.mount for /home) "
        "with dependencies, ordering, and timeout handling like any other systemd unit, and it "
        "auto-generates these from /etc/fstab at boot via systemd-fstab-generator. A matching "
        ".automount unit can defer the actual mount until the path is first accessed. "
        "systemctl status <mountpoint-name>.mount shows a mount's current state and any "
        "failure reason, which is often more informative than a bare mount error.",
        ("fstab", "automount"),
    ),
    Term(
        "removable-media",
        "Removable Media (/media, /mnt)",
        "mounting",
        "Where USB drives, SD cards, and manually mounted volumes typically show up: "
        "/media/$USER and /mnt.",
        "Desktop environments automount removable media under /media/$USER/<label-or-uuid>, "
        "keeping each user's view separate and avoiding permission clashes. /mnt is the "
        "traditional location for a system administrator to mount something by hand for a "
        "temporary task -- it has no special automount behaviour of its own, it's just a "
        "conventional empty directory reserved for this.",
        ("automount", "fhs"),
    ),
    Term(
        "network-mounts",
        "Network Mounts (NFS, SMB/CIFS, sshfs)",
        "mounting",
        "Filesystems that live on another machine but are mounted locally as if they were a "
        "local directory.",
        "NFS (Network File System) is the traditional Unix/Linux way to share a directory "
        "between machines. SMB/CIFS is the protocol Windows shares (and Samba, its Linux "
        "implementation) use, mounted on Linux with mount -t cifs or via GVFS in a file "
        "manager. sshfs mounts a remote directory over an ordinary SSH connection using FUSE, "
        "needing nothing but SSH access on the far end. All three behave like local "
        "directories once mounted, but their performance and failure modes (a dropped network "
        "link can hang I/O) differ from local disks.",
        ("fuse", "mount"),
    ),
    Term(
        "loop-mounts",
        "Loop Mounts",
        "mounting",
        "Mounting a filesystem stored inside a plain file (a .iso, a disk image, a SquashFS "
        "image) as if it were a device.",
        "A loop device lets an ordinary file be treated as a block device, so a filesystem "
        "image contained in that file can be mounted just like a real disk partition. This is "
        "how an ISO image gets mounted to browse its contents (mount -o loop file.iso /mnt), "
        "and it's the mechanism behind SquashFS-based Snap packages and live-USB images. Loop "
        "devices show up as /dev/loop0, /dev/loop1, and so on.",
        ("squashfs", "device-names"),
    ),
)

# ---- Space & Sizes ---------------------------------------------------------

_SPACE: tuple[Term, ...] = (
    Term(
        "apparent-vs-allocated-size",
        "Apparent Size vs. Allocated Size",
        "space",
        "The exact byte count of a file's contents (apparent) vs. the disk space actually "
        "reserved for it in blocks (allocated).",
        "Apparent size (st_size, what ls -l shows) is the exact number of bytes a file's "
        "contents occupy logically. Allocated size (st_blocks x 512, what du reports and what "
        "LinDriveSpace calls 'Allocated' by default) is how much space the filesystem actually "
        "reserved on disk, rounded up to whole blocks -- and, for a sparse file, potentially "
        "far less than the apparent size, since unwritten regions cost nothing. Small files "
        "nearly always show a larger allocated size than apparent size because of block "
        "rounding; this is normal and is exactly why du and ls totals disagree.",
        ("block-size", "sparse-files", "du"),
    ),
    Term(
        "sparse-files",
        "Sparse Files",
        "space",
        "Files with 'holes' -- logically large regions that were never written and cost no "
        "disk space.",
        "A sparse file is one where large ranges are logically zero-filled but were never "
        "actually written to disk, so the filesystem doesn't allocate blocks for them. Virtual "
        "machine disk images and some database files are commonly sparse. A sparse file's "
        "apparent size (what ls -l reports) can be far larger than its allocated size (what du "
        "reports); copying it with a tool that doesn't understand sparseness (like a naive cp "
        "without --sparse=auto, or many backup tools) can 'fill in' the holes and use "
        "dramatically more space than the original.",
        ("apparent-vs-allocated-size", "reflinks"),
    ),
    Term(
        "hard-links",
        "Hard Links",
        "space",
        "A second directory entry pointing at the same inode -- the same file, counted once "
        "for space purposes.",
        "A hard link is a second name for the exact same file -- same inode, same data, same "
        "permissions -- rather than a copy. Deleting one name just removes that directory "
        "entry; the file's data stays until the last link to it is removed. Because two hard "
        "links share one inode, correctly written space tools count that data once no matter "
        "how many links point to it; naively summing every path's size would double-count it. "
        "Hard links can't cross filesystems or mountpoints and, on Linux, can't target a "
        "directory.",
        ("inode", "symbolic-links"),
    ),
    Term(
        "symbolic-links",
        "Symbolic Links (Symlinks)",
        "space",
        "A small file that just stores a path to another file -- followed transparently, but "
        "never counted as the target's size.",
        "A symbolic link (symlink) is its own tiny file that stores a text path to another "
        "location; the kernel transparently redirects most operations on it to that target. "
        "Unlike a hard link, a symlink can point across filesystems, to a directory, or to a "
        "path that doesn't exist ('broken' or 'dangling'). Its own size is just the length of "
        "the path text it stores -- a space scanner should never add the target's size to it, "
        "or a handful of symlinks pointing at a huge directory could make the total look "
        "enormous.",
        ("hard-links", "path"),
    ),
    Term(
        "reflinks",
        "Reflinks / Copy-on-Write Copies",
        "space",
        "A near-instant 'copy' that shares data blocks with the original until either copy is "
        "modified.",
        "On copy-on-write filesystems (Btrfs, XFS with reflink support), cp --reflink=auto "
        "creates a new file that initially shares the same underlying data blocks as the "
        "source, instead of duplicating them -- the copy completes instantly and uses no extra "
        "space at first. Only when one of the two files is later modified does the filesystem "
        "split off new blocks for the changed part (copy-on-write). This is also the mechanism "
        "behind lightweight snapshots on these filesystems.",
        ("btrfs", "snapshots-practice"),
    ),
    Term(
        "gb-vs-gib",
        "GB vs. GiB (Decimal vs. Binary)",
        "space",
        "Why a drive sold as '1 TB' shows up as about 931 GiB: decimal marketing units vs. "
        "binary OS units.",
        "Drive manufacturers use decimal units: 1 GB = 1,000,000,000 bytes, 1 TB = "
        "1,000,000,000,000 bytes. Operating systems traditionally report binary units under "
        "the same GB/MB labels: what they call 1 GB is actually 1 GiB = 1,073,741,824 bytes "
        "(2^30). The two units diverge by about 7.4% at the gigabyte scale, which is exactly "
        "why a disk marketed as '1 TB' shows up as roughly 931 GiB in a file manager or in df. "
        "Strictly, GiB/MiB/KiB are the correct binary-unit names; LinDriveSpace lets you choose "
        "decimal or binary display in Settings.",
        (),
    ),
    Term(
        "metadata-overhead",
        "Metadata Overhead",
        "space",
        "Space a filesystem spends on its own bookkeeping -- inodes, directory entries, "
        "journals -- separate from your files' contents.",
        "Beyond the bytes a file's contents occupy, a filesystem spends space recording who "
        "owns it, its permissions, timestamps, and where its data blocks are (the inode), plus "
        "the directory entry that names it, and journal space for crash safety. This overhead "
        "is usually small per file but adds up across millions of tiny files, and it's part of "
        "why a filesystem's total 'used' space, as df reports it, is always somewhat more than "
        "the sum of visible file sizes.",
        ("inode", "reserved-blocks"),
    ),
    Term(
        "reserved-space",
        "Reserved Space",
        "space",
        "Space set aside and unavailable for ordinary allocation -- the ext root reserve, or "
        "space an application pre-allocates.",
        "'Reserved' space covers a few different things: the ext filesystem's root-only "
        "reserve (5% by default), space a program pre-allocates ahead of writing to it (a "
        "database log, a VM disk image), and swap space set aside for memory paging. In every "
        "case, df counts it as used or unavailable even though no ordinary file makes it "
        "obviously visible, which is a common reason 'used + visible files does not equal "
        "total.'",
        ("reserved-blocks", "swap", "used-free-total"),
    ),
    Term(
        "used-free-total",
        "Used + Free ≠ Total (why the numbers don't add up)",
        "space",
        "df's used and available figures can sum to less than the total, because of the root "
        "reserve and rounding.",
        "On an ext filesystem, df's 'used' plus 'available' columns commonly add up to less "
        "than the 'total' column, because the root-only reserved blocks count toward neither "
        "an ordinary user's 'available' figure nor get separately itemised. Rounding between "
        "binary and decimal units, and filesystem overhead not attributed to any single file, "
        "add smaller discrepancies of their own. None of this is a bug -- it's just several "
        "different definitions of 'space' being reported side by side.",
        ("df", "reserved-blocks", "gb-vs-gib"),
    ),
    Term(
        "percent-of-parent",
        "Percent of Parent",
        "space",
        "A folder's size expressed as a share of its immediate parent's size, for quickly "
        "spotting what's dominating a directory.",
        "Percent-of-parent shows a subfolder's size as a percentage of the folder directly "
        "containing it (not of the whole disk), which makes it easy to see at a glance which "
        "item is dominating a given level of the tree -- a folder that's 80% of its parent is "
        "almost certainly worth investigating first. LinDriveSpace shows this per row in the "
        "Explorer tree-table alongside absolute size.",
        ("du",),
    ),
    Term(
        "deleted-but-open-files",
        "Deleted-but-Open Files",
        "space",
        "A file removed from its directory but still consuming disk space, because a running "
        "process still has it open.",
        "Unix filesystems don't actually free a file's data blocks until its link count "
        "reaches zero and no process still has it open. That means a process can rm a file -- "
        "it disappears from directory listings -- while continuing to write to it, and the "
        "space it occupies stays used until that process closes the file or exits. This "
        "commonly explains a disk that du or a file browser says is nearly empty while df "
        "insists it's nearly full; lsof | grep deleted finds the culprit processes.",
        ("hard-links", "df", "du"),
    ),
    Term(
        "trash",
        "Trash (~/.local/share/Trash)",
        "space",
        "The desktop's Recycle-Bin equivalent -- deleted files move here first and still "
        "occupy their original space until emptied.",
        "File managers implement the freedesktop.org Trash specification: a 'delete' from "
        "Nautilus/Nemo moves the file into ~/.local/share/Trash/files (with metadata in "
        ".../info) rather than removing it immediately, so it's recoverable. Until the trash "
        "is emptied, those files still occupy exactly the disk space they did before, which is "
        "a common reason 'deleting' things doesn't immediately free space that df or "
        "LinDriveSpace reports.",
        ("use-trash-not-rm",),
    ),
    Term(
        "log-growth",
        "Journal / Log Growth",
        "space",
        "systemd's journal and other logs can grow large over time if never trimmed, quietly "
        "consuming disk space.",
        "systemd-journald stores logs in a binary journal, usually under /var/log/journal, and "
        "by default caps itself around 10% of the filesystem it lives on (or a configured "
        "limit) -- but on a small root partition that can still be a meaningful chunk of "
        "space. journalctl --disk-usage shows current size, and journalctl "
        "--vacuum-size=200M (or --vacuum-time=2weeks) trims it. Traditional rotated text logs "
        "under /var/log are usually managed by logrotate, which can similarly be tuned if "
        "they're consuming unexpected space.",
        ("var-directory",),
    ),
    Term(
        "package-caches",
        "Package Caches",
        "space",
        "Downloaded package files that package managers keep around after installing -- apt's "
        ".deb cache, pip's wheel cache, old Snap revisions, Flatpak runtimes.",
        "apt keeps downloaded .deb files in /var/cache/apt/archives until cleared with apt "
        "clean or apt autoclean. pip caches downloaded wheels under ~/.cache/pip. Snap keeps a "
        "configurable number of old revisions of each installed snap on disk (by default "
        "enough for rollback), reclaimable with snap set system refresh.retain=2 plus removing "
        "old revisions. Flatpak keeps shared runtimes that multiple apps depend on, cleanable "
        "of unused ones with flatpak uninstall --unused. All of these are safe to clear when "
        "space is tight, at the cost of needing to re-download if needed again.",
        ("clean-caches-safely",),
    ),
    Term(
        "thumbnails-cache",
        "Thumbnails & ~/.cache",
        "space",
        "Generated preview images and other regenerable data that file managers and apps keep "
        "under ~/.cache.",
        "File managers generate and cache thumbnail previews for images and videos, typically "
        "under ~/.cache/thumbnails, and many other applications keep their own regenerable "
        "data under ~/.cache. None of it is irreplaceable -- everything there can be deleted, "
        "and applications simply regenerate what they need next time, at the cost of a brief "
        "delay (e.g. thumbnails rebuilding) after a large cache clear.",
        ("package-caches", "clean-caches-safely"),
    ),
    Term(
        "swap",
        "Swap (file or partition)",
        "space",
        "Disk space the kernel uses to hold memory pages that don't fit in RAM, and "
        "(optionally) to support hibernation.",
        "Swap extends usable memory by letting the kernel move infrequently used RAM pages out "
        "to disk, freeing physical RAM for active work -- at a large performance cost if it's "
        "used heavily, since disk is far slower than RAM. It can be a dedicated swap partition "
        "or a swap file (the common default on modern Ubuntu/Mint installs, since it's easier "
        "to resize). Swap space shows up in free and, for a swap partition, in df-adjacent "
        "tools as its own block device, but a swap file's space is counted against its "
        "containing filesystem.",
        ("hibernation", "reserved-space"),
    ),
    Term(
        "hibernation",
        "Hibernation",
        "space",
        "Suspending to disk: the entire contents of RAM are written to swap, letting the "
        "machine power off completely and resume later.",
        "Hibernation saves a complete image of RAM to swap space (a partition or, with extra "
        "setup, a swap file) and then powers the machine off entirely; on the next boot, the "
        "kernel detects the saved image and restores it instead of doing a normal startup, "
        "resuming exactly where it left off. It needs swap space at least as large as "
        "installed RAM, which is a common reason swap is sized generously even on a machine "
        "that rarely runs low on memory.",
        ("swap",),
    ),
)

# ---- Directories & the Tree -------------------------------------------------

_DIRECTORIES: tuple[Term, ...] = (
    Term(
        "directory-vs-folder",
        "Directory vs. Folder",
        "directories",
        'The same thing: "directory" is the Unix/technical term, "folder" is the desktop '
        "metaphor for it.",
        "A directory and a folder are the same object on disk -- a special kind of file that "
        'holds a list of names pointing to other files and directories. "Directory" is the '
        'term Unix and Linux tools (mkdir, cd, rmdir) and documentation use; "folder" is the '
        "visual metaphor desktop environments (Nautilus, Nemo, Windows Explorer) use for the "
        'same thing, borrowed from paper filing folders. LinDriveSpace uses "folder" in most '
        'of its UI copy and "directory" in more technical contexts, but they always mean the '
        "same underlying structure.",
        ("path", "fhs"),
    ),
    Term(
        "fhs",
        "Filesystem Hierarchy Standard (FHS)",
        "directories",
        "The convention that says what each top-level directory is for: /home for users, /etc "
        "for config, /var for changing data, and so on.",
        "The FHS is the widely followed convention (not strictly enforced by the kernel) for "
        "what belongs where in the Linux directory tree. Roughly: / is the root of everything; "
        "/home holds personal user data; /root is the root account's home; /etc holds "
        "system-wide configuration; /var holds data that changes at runtime (logs, caches, "
        "spool); /tmp holds temporary files that may be cleared on reboot; /usr holds "
        "installed programs and their data; /opt holds self-contained third-party software; "
        "/srv holds data served by this machine (e.g. a web or FTP root); /boot holds the "
        "kernel and bootloader files; /dev, /proc, /sys, and /run are kernel-managed pseudo or "
        "runtime filesystems rather than real storage; /snap holds mounted Snap packages; "
        "/mnt and /media are conventional mount locations; and lost+found is where fsck "
        "deposits recovered orphaned files after a repair. Following the FHS is what lets any "
        "Linux tool assume, correctly, where to find or put things.",
        ("root-directory", "home-directory", "etc-directory", "var-directory"),
    ),
    Term(
        "root-directory",
        "/ (Root Directory)",
        "directories",
        "The top of the whole filesystem tree -- every other path is somewhere underneath it.",
        "/ is the root of the entire directory tree: every absolute path starts from it, and "
        "every other mounted filesystem attaches somewhere underneath it. The partition "
        "mounted at / holds the base operating system unless specific subtrees (like /home) "
        "are split onto their own partitions. If / fills up completely, the system can become "
        "unstable or unable to start new processes, since many core services need to write "
        "small amounts of data even during normal operation.",
        ("mountpoint", "avoid-filling-root"),
    ),
    Term(
        "home-directory",
        "/home",
        "directories",
        "Where each user's personal files, settings, and desktop live, one subdirectory per user.",
        "/home holds one subdirectory per user (e.g. /home/alice) containing that user's "
        "documents, downloads, application settings (often in dotfiles), and desktop "
        "configuration. It's commonly put on its own partition separate from /, so the "
        "operating system can be reinstalled or upgraded without touching personal data.",
        ("separate-home-partition", "dotfiles"),
    ),
    Term(
        "etc-directory",
        "/etc",
        "directories",
        "System-wide configuration files -- no executables, just config.",
        "/etc holds machine-wide configuration: /etc/fstab (mounts), /etc/passwd (user "
        "accounts), network and service configuration, and most package configuration files. "
        "Its name traditionally stood for 'et cetera' from early Unix, where miscellaneous "
        "system files ended up; today it's specifically reserved for configuration.",
        ("fstab",),
    ),
    Term(
        "var-directory",
        "/var",
        "directories",
        "Data that changes while the system runs: logs, caches, spool files, package databases.",
        "/var ('variable') holds data expected to grow and change during normal operation, as "
        "opposed to /usr's mostly-static installed programs. It includes /var/log (system and "
        "application logs), /var/cache (regenerable cached data, including package manager "
        "caches), /var/spool (queued print or mail jobs), and /var/lib (persistent application "
        "state, like package databases). It's a common target for disk-space investigation "
        "since logs and caches can grow unexpectedly.",
        ("log-growth", "package-caches"),
    ),
    Term(
        "tmp-directory",
        "/tmp",
        "directories",
        "Shared scratch space for temporary files -- world-writable, and traditionally "
        "protected by the sticky bit.",
        "/tmp is writable by every user for temporary files, and on many systems is cleared "
        "automatically on reboot (or via systemd-tmpfiles). Because it's shared and "
        "world-writable, it has the sticky bit set, which stops one user from deleting or "
        "renaming files another user put there. It's sometimes mounted as tmpfs (RAM-backed) "
        "for speed, which means anything in it also disappears immediately on unmount, not "
        "just on reboot.",
        ("sticky-bit", "tmpfs"),
    ),
    Term(
        "boot-directory",
        "/boot",
        "directories",
        "The kernel, initramfs, and bootloader configuration needed to start the system.",
        "/boot holds the files the bootloader needs before the rest of the OS is even "
        "reachable: the kernel image (vmlinuz), the initial RAM filesystem (initrd/initramfs), "
        "and GRUB's configuration. It's often kept on its own smallish partition, and on a "
        "UEFI system typically contains or sits alongside /boot/efi, the mounted EFI System "
        "Partition. It can fill up on systems that don't clean up old kernel versions after "
        "upgrades.",
        ("efi-system-partition",),
    ),
    Term(
        "proc-directory",
        "/proc",
        "directories",
        "A virtual, kernel-generated view of running processes and kernel state -- not real "
        "files on disk.",
        "/proc is generated live by the kernel and contains no real files: /proc/<pid>/ "
        "exposes information about each running process, and files like /proc/meminfo, "
        "/proc/cpuinfo, and /proc/self/mountinfo expose kernel state. Its reported sizes are "
        "nominal (usually 0 bytes), and it must never be scanned, backed up, or deleted from "
        "as if it were ordinary storage.",
        ("pseudo-filesystems", "dont-delete-pseudo-fs"),
    ),
    Term(
        "sys-directory",
        "/sys",
        "directories",
        "The kernel's device and driver model exposed as a virtual directory tree, used to "
        "inspect and tune hardware.",
        "/sys (sysfs) exposes the kernel's internal object model for devices, drivers, and "
        "buses as a browsable tree of virtual files -- for example, a disk's queue scheduler "
        "is readable and settable under /sys/block/sda/queue/scheduler. Like /proc, it holds "
        "no real data on disk and shouldn't be treated as a normal directory for space or "
        "backup purposes.",
        ("pseudo-filesystems", "io-scheduler"),
    ),
    Term(
        "dev-directory",
        "/dev",
        "directories",
        "Device nodes -- special files representing hardware and virtual devices, not files "
        "with content of their own.",
        "/dev holds device nodes such as /dev/sda (a whole disk), /dev/null, and /dev/zero -- "
        "special files that represent devices rather than store data themselves. It's normally "
        "mounted as devtmpfs, populated automatically by the kernel and udev as hardware is "
        "detected, rather than being a real on-disk directory an administrator edits by hand.",
        ("device-names", "hotplug-udev"),
    ),
    Term(
        "dotfiles",
        "Dotfiles / Hidden Files",
        "directories",
        "Files and directories whose name starts with a dot -- hidden from a normal file "
        "listing by convention, not by permission.",
        "Any file or directory beginning with a period, like .bashrc or .config, is treated as "
        "'hidden' by convention: ls omits it unless you pass -a, and file managers hide it "
        "unless 'show hidden files' is toggled. This is purely a display convention, not a "
        "security mechanism -- hidden files are exactly as readable and writable as any other "
        "file, given the right permissions. Application configuration commonly lives in "
        "dotfiles or dot-directories under a user's home directory (~/.config is the modern "
        "convention for this).",
        ("home-directory", "permissions-denied"),
    ),
    Term(
        "permissions-denied",
        'Permissions & "Access Denied"',
        "directories",
        "Why a scanner (or you) can be refused entry into some folders: Unix read/write/"
        "execute permissions per owner, group, and everyone else.",
        "Every file and directory carries permission bits for its owner, its group, and "
        "everyone else, covering read, write, and execute (for a directory, execute means "
        "'allowed to look inside'). A folder owned by another user or by root with no "
        "read/execute bits for you will refuse a plain listing -- this is why an unprivileged "
        "disk scan can show some folders as inaccessible, and why LinDriveSpace offers a "
        "privileged ('scan as administrator') mode via polkit for a complete picture.",
        ("ownership", "polkit"),
    ),
    Term(
        "ownership",
        "Ownership (user & group)",
        "directories",
        "Every file belongs to one user and one group, which combine with permission bits to "
        "decide who can do what to it.",
        "Every file and directory has exactly one owning user and one owning group; permission "
        "bits are then interpreted relative to whichever of the three categories (owner, "
        "group, other) the requesting process falls into. chown changes the owning "
        "user/group, chmod changes the permission bits. A common source of confusion is a file "
        "owned by root ending up in a user's directory (for example after running a command "
        "with sudo), which then denies that user normal write access to their own file.",
        ("permissions-denied",),
    ),
    Term(
        "sticky-bit",
        "Sticky Bit",
        "directories",
        "A permission flag on a shared, writable directory (like /tmp) that stops users from "
        "deleting each other's files.",
        "The sticky bit, set on a directory (visible as a 't' in the permissions column, e.g. "
        "drwxrwxrwt), restricts deletion and renaming inside it: even though the directory is "
        "writable by everyone, only a file's owner (or root) can remove or rename that "
        "specific file. /tmp is the classic example -- it needs to be writable by every user, "
        "but without the sticky bit any user could delete anyone else's temporary files.",
        ("tmp-directory", "permissions-denied"),
    ),
    Term(
        "path",
        "Path",
        "directories",
        "The string that names a location in the filesystem tree, using / to separate directories.",
        "A path describes where a file or directory sits in the tree by listing the "
        "directories to pass through, separated by '/', ending in the file or directory's own "
        "name. Linux paths use forward slashes (unlike Windows' backslashes) and are "
        "case-sensitive. A path can be absolute or relative to wherever the shell or program "
        "currently 'is.'",
        ("absolute-vs-relative", "directory-vs-folder"),
    ),
    Term(
        "absolute-vs-relative",
        "Absolute vs. Relative Paths",
        "directories",
        "An absolute path starts from / and always means the same location; a relative path "
        "depends on the current working directory.",
        "An absolute path starts with '/' and unambiguously names one location regardless of "
        "where it's used from, e.g. /home/alice/Documents. A relative path, like Documents or "
        "../backups, is interpreted starting from the current working directory, so the same "
        "relative path can point to different places depending on where a command is run. "
        "Scripts and configuration that need to be reliable regardless of context (like "
        "/etc/fstab entries) always use absolute paths.",
        ("path", "working-directory"),
    ),
    Term(
        "working-directory",
        "Working Directory",
        "directories",
        'The directory a running process or shell session is currently "in," against which '
        "relative paths are resolved.",
        "The working directory (or 'current directory') is the reference point every process "
        "has for resolving relative paths. In a shell, cd changes it; pwd prints it. It's also "
        "why a still-open shell or process can keep a filesystem 'busy' and refuse to unmount "
        "-- its working directory sits somewhere inside that mount, even if it isn't actively "
        "reading or writing.",
        ("absolute-vs-relative", "unmount"),
    ),
)

# ---- Storage Subsystems -----------------------------------------------------

_SUBSYSTEMS: tuple[Term, ...] = (
    Term(
        "vfs",
        "VFS (Virtual Filesystem)",
        "subsystems",
        "The kernel's abstraction layer that makes ext4, Btrfs, NFS, FUSE, and every other "
        "filesystem look the same to programs.",
        "The VFS is the layer inside the Linux kernel that presents one consistent interface "
        "-- open, read, write, readdir, and so on -- regardless of which actual filesystem "
        "driver handles a given path. It's what lets a single open() system call work "
        "identically whether the target file lives on ext4, Btrfs, an NFS share, or a FUSE "
        "mount, and it's why new filesystem types can be added without changing every "
        "application that uses files.",
        ("fuse", "page-cache"),
    ),
    Term(
        "page-cache",
        "Page Cache",
        "subsystems",
        "RAM the kernel uses to hold recently read or written disk data, so repeat access is "
        "fast without touching the disk again.",
        "The page cache holds copies of disk data in otherwise-unused RAM, so a file read a "
        "second time can often be served straight from memory instead of hitting the disk. "
        "Linux uses free RAM for this aggressively and reclaims it on demand, which is why "
        "free typically shows most RAM as 'used' -- that's mostly reclaimable cache, not "
        "memory unavailable to applications. Writes normally land in the page cache first and "
        "are flushed to disk asynchronously, which is part of why sync and clean unmounts "
        "matter.",
        ("vfs", "swap"),
    ),
    Term(
        "block-layer",
        "Block Layer",
        "subsystems",
        "The kernel subsystem that queues, merges, and schedules I/O requests between "
        "filesystems and physical storage devices.",
        "The block layer sits between filesystems (and the page cache) above and physical "
        "storage drivers below, managing the queue of pending reads and writes: merging "
        "adjacent requests, applying an I/O scheduler's policy, and handing finished requests "
        "off to the actual device driver. It's shared infrastructure used by every block "
        "device -- disks, partitions, LVM volumes, loop devices -- regardless of which "
        "filesystem sits on top.",
        ("io-scheduler", "block-device"),
    ),
    Term(
        "io-scheduler",
        "I/O Scheduler",
        "subsystems",
        "The block layer's policy for ordering pending disk requests -- mq-deadline, bfq, or none.",
        "An I/O scheduler decides the order in which queued disk requests are actually issued "
        "to the device, trading off throughput, latency, and fairness between processes. none "
        "does no reordering, appropriate for fast NVMe drives whose own controller already "
        "handles scheduling. mq-deadline bounds how long any single request can wait, a solid "
        "general-purpose default. bfq (Budget Fair Queueing) aims for interactive "
        "responsiveness -- keeping the desktop snappy even while a large background copy runs "
        "-- at some cost to raw throughput, and suits spinning disks well. The active scheduler "
        "per device is readable/settable under /sys/block/<dev>/queue/scheduler.",
        ("block-layer", "sys-directory"),
    ),
    Term(
        "device-mapper",
        "Device Mapper",
        "subsystems",
        "The kernel framework that builds virtual block devices out of others -- the "
        "foundation LVM and LUKS are built on.",
        "Device Mapper is a generic framework for creating virtual block devices that "
        "transform or combine other block devices underneath them, showing up as /dev/dm-0, "
        "/dev/dm-1, and so on (or friendlier names under /dev/mapper/). LVM logical volumes, "
        "LUKS-encrypted containers, and software RAID targets are all, under the hood, "
        "device-mapper devices -- it's the shared plumbing several higher-level storage "
        "features build on.",
        ("lvm", "luks-dmcrypt", "device-names"),
    ),
    Term(
        "lvm",
        "LVM (Logical Volume Manager)",
        "subsystems",
        "A layer between partitions and filesystems that lets storage be resized, combined, "
        "and snapshotted flexibly.",
        "LVM groups one or more physical partitions or disks (Physical Volumes) into a pool (a "
        "Volume Group), then carves that pool into Logical Volumes that behave like regular "
        "partitions but can be resized, moved, or extended across physical devices without "
        "repartitioning. It also supports thin provisioning, where logical volumes are "
        "allocated more nominal space than physically exists, with real blocks only consumed "
        "as data is actually written -- useful for flexible-sized virtual machine disks, but "
        "risky if the pool isn't monitored, since it can fill up unexpectedly.",
        ("device-mapper",),
    ),
    Term(
        "luks-dmcrypt",
        "LUKS / dm-crypt",
        "subsystems",
        "Full-disk or partition encryption on Linux: dm-crypt does the encrypting, LUKS is the "
        "standard on-disk format and key management around it.",
        "dm-crypt is the kernel's transparent block-device encryption layer, and LUKS (Linux "
        "Unified Key Setup) is the standard format it uses for storing encryption metadata and "
        "multiple possible unlock passphrases/keys on the encrypted device itself. An "
        "encrypted partition is unlocked (typically at boot, via a passphrase prompt) into a "
        "virtual device-mapper block device that the rest of the system then treats as an "
        "ordinary, already-decrypted partition.",
        ("device-mapper",),
    ),
    Term(
        "mdadm-raid",
        "mdadm / Software RAID",
        "subsystems",
        "Combining several disks into one logical array for redundancy and/or speed, managed "
        "in software by the kernel's md driver.",
        "Linux software RAID (managed with mdadm) combines multiple block devices into one "
        "array using the kernel's md driver. RAID 0 stripes data across disks for speed with "
        "no redundancy; RAID 1 mirrors data across disks for redundancy at the cost of usable "
        "capacity; RAID 5/6 stripe data with parity, tolerating one or two disk failures "
        "respectively at lower capacity overhead than mirroring. The resulting array appears "
        "as a single block device (e.g. /dev/md0) that a filesystem is then created on "
        "directly, same as any partition.",
        ("device-mapper",),
    ),
    Term(
        "udev",
        "udev",
        "subsystems",
        "The subsystem that creates /dev device nodes and runs rules in response to hardware "
        "appearing or disappearing.",
        "udev listens for kernel events about hardware being added or removed and reacts by "
        "creating or removing the corresponding /dev entries, applying naming rules (like "
        "stable /dev/disk/by-id symlinks), setting permissions, and triggering follow-up "
        "actions such as automount. It replaced the older static /dev populated at install "
        "time with a fully dynamic one that reflects only hardware actually present.",
        ("systemd-udevd", "hotplug-udev"),
    ),
    Term(
        "systemd-udevd",
        "systemd-udevd",
        "subsystems",
        "The daemon that implements udev's device-event handling as part of systemd.",
        "systemd-udevd is the actual daemon process that carries out udev's job: receiving "
        "kernel uevents, matching them against rule files (mostly under "
        "/usr/lib/udev/rules.d/ and /etc/udev/rules.d/), and creating device nodes, symlinks, "
        "and permissions accordingly. It's why a freshly plugged-in USB drive gets a working "
        "/dev/sdX node, correct permissions, and a udisks2-triggered automount within a "
        "fraction of a second, with no manual step.",
        ("udev", "automount"),
    ),
    Term(
        "polkit",
        "Polkit",
        "subsystems",
        "The framework that governs privileged actions on a Linux desktop -- why a full disk "
        "scan can prompt for a password.",
        "Polkit (PolicyKit) lets an unprivileged desktop application request a specific "
        "privileged action (mounting a device it doesn't own, or, for LinDriveSpace, scanning "
        "paths an ordinary user can't read) through a well-defined policy, rather than needing "
        "the whole application to run as root. When such an action is requested, polkit's "
        "agent shows an authentication prompt; approving it grants just that action, not a "
        "root shell. It's the mechanism behind LinDriveSpace's 'scan as administrator' option.",
        ("permissions-denied",),
    ),
    Term(
        "io-uring",
        "io_uring",
        "subsystems",
        "A modern Linux kernel interface for asynchronous I/O, using shared ring buffers to "
        "avoid a system call per operation.",
        "io_uring lets a program submit I/O requests and collect their results through ring "
        "buffers shared with the kernel, avoiding the per-operation system-call overhead of "
        "older async I/O interfaces. It's increasingly used by high-performance storage and "
        "networking software where issuing thousands of small operations per second would "
        "otherwise be dominated by system-call cost rather than actual I/O.",
        ("block-layer",),
    ),
    Term(
        "nvme-queues",
        "NVMe Queues",
        "subsystems",
        "NVMe drives support thousands of parallel command queues, letting many CPU cores "
        "issue storage I/O simultaneously with minimal contention.",
        "Unlike SATA's single command queue, the NVMe protocol supports up to 64,000 queues "
        "with up to 64,000 commands each, and typically gives each CPU core its own queue "
        "pair. That parallelism, combined with running directly over PCIe rather than through "
        "a SATA controller, is the main reason NVMe drives sustain far higher IOPS and lower "
        "latency than SATA SSDs under concurrent load.",
        ("ssd-vs-hdd-vs-nvme",),
    ),
    Term(
        "sata-ahci",
        "SATA / AHCI",
        "subsystems",
        "The traditional interface and command protocol most non-NVMe disks and SSDs still "
        "use to talk to the system.",
        "SATA (Serial ATA) is the physical/electrical interface most HDDs and older or budget "
        "SSDs use to connect to a system; AHCI (Advanced Host Controller Interface) is the "
        "standard way the operating system talks to a SATA controller. AHCI supports Native "
        "Command Queuing (up to 32 outstanding commands in one queue), a big improvement over "
        "even older IDE-mode operation, but still far less parallel than NVMe's many "
        "independent queues.",
        ("nvme-queues", "ssd-vs-hdd-vs-nvme"),
    ),
    Term(
        "usb-mass-storage-uas",
        "USB Mass Storage / UAS",
        "subsystems",
        "The two protocols USB drives use to present themselves as disks: the older, simpler "
        "Mass Storage class, and the faster UAS.",
        "USB Mass Storage (BOT, 'Bulk-Only Transport') is the original, simple, "
        "one-command-at-a-time protocol most USB flash drives and external HDDs use. UAS (USB "
        "Attached SCSI) is a newer protocol that allows command queuing similar to AHCI/NVMe, "
        "giving better performance for drives and enclosures that support it (commonly USB "
        "3.0+ SSD enclosures). Linux picks whichever the device advertises automatically; "
        "lsusb and kernel logs show which driver attached.",
        ("scsi",),
    ),
    Term(
        "scsi",
        "SCSI",
        "subsystems",
        "A long-standing command set for talking to storage devices; still used as the command "
        "language under SATA, USB storage, and more.",
        "SCSI (Small Computer System Interface) began as a physical bus and protocol for "
        "connecting storage devices, but today its command set lives on as the language many "
        "other transports speak underneath -- SATA disks, USB mass-storage devices, and others "
        "all get exposed to Linux through the kernel's SCSI subsystem, which is part of why "
        "SATA disks appear as /dev/sdX ('sd' for SCSI Disk) rather than a SATA-specific name.",
        ("usb-mass-storage-uas", "sata-ahci"),
    ),
    Term(
        "mmc-sd",
        "MMC / SD",
        "subsystems",
        "The interface used by SD cards, microSD cards, and the eMMC flash storage soldered "
        "onto many small devices.",
        "MMC (MultiMediaCard) and its SD (Secure Digital) descendant are the interface used by "
        "removable SD/microSD cards, and eMMC is essentially the same technology soldered "
        "directly onto a board, common in inexpensive laptops, tablets, and single-board "
        "computers like the Raspberry Pi. On Linux these devices appear as /dev/mmcblk0 (whole "
        "device) and /dev/mmcblk0p1 (partition), distinct from the /dev/sdX naming used for "
        "SCSI/SATA/USB-storage disks.",
        ("device-names",),
    ),
)

# ---- Best Practices ---------------------------------------------------------

_PRACTICES: tuple[Term, ...] = (
    Term(
        "keep-free-space",
        "Keep 10-15% Free",
        "practices",
        "Leaving headroom on a volume avoids ext4 fragmentation and lets SSDs perform their "
        "own background maintenance well.",
        "Filesystems, ext4 especially, get measurably more fragmented and slower at finding "
        "good contiguous allocations once they're consistently very full -- keeping roughly "
        "10-15% free gives the allocator room to work. On SSDs, free space also functions as "
        "informal over-provisioning: more spare blocks for the controller's wear levelling and "
        "garbage collection to use, which keeps write performance from degrading as the drive "
        "ages. Both are good reasons to treat 'nearly full' as worth addressing well before a "
        "volume hits 0% free.",
        ("ssd-vs-hdd-vs-nvme", "wear-levelling"),
    ),
    Term(
        "separate-home-partition",
        "Separate /home Partition",
        "practices",
        "Keeping personal data on its own partition lets the OS be reinstalled or upgraded "
        "without touching it.",
        "Putting /home on a partition separate from / means a distribution reinstall, or even "
        "a switch to a different distribution, can reformat only the root partition and leave "
        "personal files, application settings, and dotfiles completely untouched. The main "
        "trade-off is that / and /home then have independent free-space limits, so a full "
        "/home doesn't automatically borrow space from an otherwise-empty root partition.",
        ("home-directory", "root-directory"),
    ),
    Term(
        "backup-before-resizing",
        "Back Up Before Resizing",
        "practices",
        "Partition and filesystem resizing is generally safe today, but a power loss or bug "
        "mid-operation can still cause data loss -- back up first.",
        "Resizing a partition or its filesystem (shrinking, growing, or moving it) is "
        "well-supported by modern tools like GParted, but the operation rewrites core "
        "filesystem structures and, for a shrink, must first ensure no data sits beyond the "
        "new boundary. An interruption -- a power cut, a crash -- partway through is one of "
        "the few remaining ways to lose an entire filesystem's contents, so a backup of "
        "anything irreplaceable beforehand is standard, cheap insurance.",
        ("snapshots-practice",),
    ),
    Term(
        "snapshots-practice",
        "Use Snapshots for Fast, Cheap Recovery Points",
        "practices",
        "Timeshift, or native Btrfs snapshots, let you roll back a bad update or accidental "
        "deletion in seconds.",
        "A snapshot captures a filesystem's state at a point in time without copying all the "
        "data up front, using copy-on-write so only later changes consume extra space. "
        "Timeshift (common on Linux Mint) automates this using rsync-based hard-link snapshots "
        "on ext4 or native snapshots on Btrfs, letting a bad system update or configuration "
        "change be rolled back in a couple of clicks. Snapshots are not a substitute for an "
        "off-disk backup -- a drive failure or ransomware-style event takes the snapshots down "
        "with the live data -- but they're excellent cheap insurance against everyday "
        "mistakes.",
        ("btrfs", "reflinks"),
    ),
    Term(
        "clean-caches-safely",
        "Clean Caches Safely",
        "practices",
        "Package caches, thumbnail caches, and browser caches are safe to clear; treat "
        "anything unfamiliar with more caution.",
        "Directories explicitly meant as caches -- package manager download caches, ~/.cache, "
        "browser caches -- are designed to be cleared at any time; the owning application "
        "simply regenerates or re-downloads what it needs next. The safe rule of thumb: clear "
        "things that are labelled or conventionally understood as cache or temp data, and "
        "leave alone anything you can't positively identify, especially inside /var/lib, /etc, "
        "or any path outside your own home directory, without first checking what depends on "
        "it.",
        ("package-caches", "thumbnails-cache"),
    ),
    Term(
        "dont-delete-pseudo-fs",
        "Never Delete Inside /proc, /sys, /dev",
        "practices",
        "These are kernel-generated views, not storage -- 'cleaning' them makes no space and "
        "can destabilize a running system.",
        "/proc, /sys, and /dev contain no real files to reclaim space from -- they're live, "
        "kernel-generated representations of processes, hardware, and devices, regenerated on "
        "the fly. Deleting or modifying entries in them doesn't free any disk space and can "
        "interfere with running processes or hardware access; a disk-space tool (including "
        "LinDriveSpace) should treat them as out of scope entirely rather than something to "
        "clean up.",
        ("pseudo-filesystems",),
    ),
    Term(
        "use-trash-not-rm",
        "Use Trash, Not rm, for Anything You Might Want Back",
        "practices",
        "Deleting through a file manager's Trash is recoverable; rm (and Shift+Delete) is not.",
        "Moving a file to Trash through a file manager is reversible -- the file sits in "
        "~/.local/share/Trash until you empty it. Removing a file with rm at a terminal, or "
        "bypassing Trash in a file manager (often Shift+Delete), deletes it immediately with "
        "no built-in recovery path; the space becomes reusable right away, but so does any "
        "chance of getting the file back short of specialist data-recovery tools, and even "
        "then only if nothing has overwritten those blocks since.",
        ("trash",),
    ),
    Term(
        "check-df-du",
        "Check df -h and du -sh Before Guessing",
        "practices",
        "Confirm which filesystem is actually full (df) and which folder is actually large "
        "(du) before acting.",
        "df -h quickly shows which mounted filesystem is actually the one running low, since a "
        "user can easily be looking at the wrong drive or mountpoint. du -sh <folder> on a "
        "suspected culprit confirms its real footprint before you spend time investigating or "
        "deleting things. Running both first, rather than guessing from folder names or vague "
        "impressions, avoids wasted effort -- and it's exactly what LinDriveSpace's Overview "
        "and Explorer pages automate and present visually.",
        ("df", "du"),
    ),
    Term(
        "trim-weekly",
        "Enable fstrim.timer (Weekly TRIM)",
        "practices",
        "A periodic TRIM pass keeps an SSD's free-block pool healthy without the latency cost "
        "of continuous discard.",
        "Most current Ubuntu/Mint installs enable the fstrim.timer systemd unit by default, "
        "which runs fstrim across all TRIM-capable mounted filesystems roughly once a week. "
        "This is generally preferred over the discard mount option (continuous TRIM on every "
        "deletion), since continuous discard can add small latency spikes to write-heavy "
        "workloads, while a weekly batch pass gets nearly all the same long-term benefit. "
        "systemctl status fstrim.timer confirms it's active.",
        ("trim",),
    ),
    Term(
        "monitor-smart-practice",
        "Monitor SMART Health",
        "practices",
        "Periodically checking SMART attributes catches a failing drive before it takes data "
        "down with it.",
        "Installing smartmontools and either running smartctl -a /dev/sdX occasionally or "
        "enabling its background daemon (smartd) to email on threshold breaches gives early "
        "warning of a degrading drive -- rising reallocated sector counts, a failed self-test, "
        "or falling SSD endurance -- well before a filesystem error or total failure. Catching "
        "this early is the difference between a calm planned replacement and an emergency "
        "data-recovery situation.",
        ("smart",),
    ),
    Term(
        "label-partitions-practice",
        "Label Your Partitions",
        "practices",
        "A clear label makes a partition identifiable at a glance in any tool, instead of a "
        "bare, easily-confused /dev/sdX name.",
        "Setting a filesystem label (e.g. 'DATA', 'BACKUP', 'Mint-root') at format time, or "
        "later with a tool like e2label, makes that partition recognisable immediately in a "
        "file manager, in GParted, or in lsblk -f, rather than requiring you to remember which "
        "/dev/sdXN number it currently happens to have -- a number that can shift if drives "
        "are added, removed, or reordered.",
        ("label", "uuid"),
    ),
    Term(
        "gpt-for-new-disks",
        "Use GPT for New Disks",
        "practices",
        "GPT is the modern default: it supports large disks, many partitions, and is required "
        "for UEFI booting.",
        "Unless a specific piece of legacy software requires the old MBR scheme, new disks "
        "should be partitioned with GPT: it removes MBR's four-primary-partition and 2 TiB "
        "size limits, and it's a prerequisite for booting via UEFI (the firmware standard on "
        "essentially all current hardware) rather than legacy BIOS compatibility mode.",
        ("partition-table", "efi-system-partition"),
    ),
    Term(
        "noatime-practice",
        "Consider noatime for Busy Filesystems",
        "practices",
        "Skipping access-time updates cuts a meaningful amount of write traffic on filesystems "
        "with lots of file reads.",
        "By default (relatime, the modern compromise), every file read still occasionally "
        "triggers a small metadata write to update its last-accessed timestamp. Mounting a "
        "filesystem with noatime skips that entirely, which reduces write traffic and, on "
        "flash storage, wear -- worthwhile on a filesystem read very frequently (mail servers, "
        "build directories) as long as nothing on the system actually depends on accurate "
        "access times (a few mail and backup tools do).",
        ("mount-options",),
    ),
    Term(
        "avoid-filling-root",
        "Never Let / Fill Completely",
        "practices",
        "A completely full root filesystem can stop the system from logging, starting new "
        "processes, or even finishing a clean shutdown.",
        "Because core system services -- logging, temporary files, package management, "
        "sometimes even login itself -- need to write small amounts of data to the root "
        "filesystem during normal operation, letting / fill to 100% can cause cascading "
        "failures well beyond just 'can't save this one file': services crash-looping, an "
        "inability to log the very error explaining what's wrong, or a system that can't "
        "complete a clean shutdown. This is a large part of why the ext root reserve exists, "
        "and why keeping headroom on / specifically, not just any large data partition, "
        "matters most.",
        ("root-directory", "reserved-blocks"),
    ),
    Term(
        "lindrivespace-numbers",
        "Where LinDriveSpace's Numbers Come From",
        "practices",
        "Sizes come from the filesystem itself (df) and from LinDriveSpace's own directory "
        "walk (du-style allocated sizes) -- the same sources described elsewhere in this "
        "glossary.",
        "The Overview page's per-mount totals come from the same kernel-reported statistics df "
        "uses. The Explorer's per-folder sizes come from LinDriveSpace walking the directory "
        "tree itself and summing each file's allocated size (matching du's convention) or "
        "apparent size (matching ls), depending on the 'Primary size' setting -- exactly the "
        "apparent-vs-allocated distinction covered elsewhere in this glossary. Hard-linked "
        "files are counted once when 'count hard links once' is enabled, matching how du "
        "behaves by default.",
        ("apparent-vs-allocated-size", "df", "hard-links"),
    ),
)

TERMS: tuple[Term, ...] = (
    _DISKS + _FILESYSTEMS + _MOUNTING + _SPACE + _DIRECTORIES + _SUBSYSTEMS + _PRACTICES
)


def by_category(cat_id: str) -> list[Term]:
    """All terms in a category, in ``TERMS`` order."""
    return [t for t in TERMS if t.category == cat_id]


def search(query: str) -> list[Term]:
    """Case-insensitive search over title, summary, and body.

    Title matches are returned first (in ``TERMS`` order), followed by
    summary/body-only matches (also in ``TERMS`` order). An empty or
    whitespace-only query returns an empty list.
    """
    q = query.strip().lower()
    if not q:
        return []
    title_hits = [t for t in TERMS if q in t.title.lower()]
    title_keys = {t.key for t in title_hits}
    other_hits = [
        t
        for t in TERMS
        if t.key not in title_keys and (q in t.summary.lower() or q in t.body.lower())
    ]
    return title_hits + other_hits


def get(key: str) -> Term | None:
    """The term with this key, or ``None``."""
    for t in TERMS:
        if t.key == key:
            return t
    return None
