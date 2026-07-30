/**
 * Vendor and distro marks.
 *
 * Drawn as inline SVG paths rather than pulled from a logo CDN: the app is
 * self-hosted and often runs on management networks with no egress, so an
 * external asset would render as a broken box exactly where it matters.
 *
 * These are simplified, recognisable-at-16px glyphs in `currentColor`, not
 * reproductions of the official brand marks — that keeps them legible in
 * both themes and avoids shipping trademarked artwork.
 */

type IconProps = React.SVGProps<SVGSVGElement>;

/** os-release ID (or ID_LIKE) → the glyph we draw for it. */
export type DistroKey =
  | "ubuntu"
  | "debian"
  | "rhel"
  | "alpine"
  | "suse"
  | "arch"
  | "linux";

const DISTRO_BY_ID: Record<string, DistroKey> = {
  ubuntu: "ubuntu",
  debian: "debian",
  linuxmint: "ubuntu",
  pop: "ubuntu",
  raspbian: "debian",
  rhel: "rhel",
  centos: "rhel",
  rocky: "rhel",
  almalinux: "rhel",
  fedora: "rhel",
  ol: "rhel",
  alpine: "alpine",
  opensuse: "suse",
  "opensuse-leap": "suse",
  "opensuse-tumbleweed": "suse",
  sles: "suse",
  arch: "arch",
  manjaro: "arch",
};

/**
 * Resolve a distro glyph.
 *
 * `os_version` carries PRETTY_NAME ("Ubuntu 24.04.1 LTS"), which is the only
 * distro detail stored per device — `os_family` collapses Rocky, Alma and
 * Fedora into "rhel", so matching the pretty name first keeps a Rocky box
 * from being drawn as generic Red Hat when we can do better.
 */
export function distroKey(
  osFamily: string | null | undefined,
  osVersion: string | null | undefined,
): DistroKey {
  const pretty = (osVersion ?? "").toLowerCase();
  for (const [id, key] of Object.entries(DISTRO_BY_ID)) {
    if (pretty.includes(id)) return key;
  }
  const family = (osFamily ?? "").toLowerCase();
  if (family in DISTRO_BY_ID) return DISTRO_BY_ID[family];
  return "linux";
}

export function distroLabel(
  osFamily: string | null | undefined,
  osVersion: string | null | undefined,
): string {
  if (osVersion) return osVersion;
  switch (osFamily) {
    case "debian":
      return "Debian family";
    case "rhel":
      return "RHEL family";
    case "alpine":
      return "Alpine";
    case "suse":
      return "SUSE";
    default:
      return "Linux";
  }
}

/** The MikroTik "R" router mark, simplified. */
export function MikrotikIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <rect
        x="2.5"
        y="7.5"
        width="19"
        height="11"
        rx="2"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path
        d="M6 15V11.2c0-.4.3-.7.7-.7h1.6c.7 0 1.2.5 1.2 1.2s-.5 1.2-1.2 1.2H6.9m2 0L10.6 15"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="15.5" cy="12.5" r="1" fill="currentColor" />
      <circle cx="18.5" cy="12.5" r="1" fill="currentColor" />
      <path
        d="M8 5.5c1.6-1.6 3-2 4-2s2.4.4 4 2"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Tux, reduced to a silhouette that survives 16px. */
export function LinuxIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path
        d="M12 2.6c2.2 0 3.4 1.7 3.4 4.1 0 1.3.3 2 1 3 1.4 2 2.6 3.4 2.6 5.6 0 2.9-2.4 5.1-7 5.1s-7-2.2-7-5.1c0-2.2 1.2-3.6 2.6-5.6.7-1 1-1.7 1-3 0-2.4 1.2-4.1 3.4-4.1Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <circle cx="10.2" cy="7.2" r="1" fill="currentColor" />
      <circle cx="13.8" cy="7.2" r="1" fill="currentColor" />
      <path
        d="M10.6 10.1c.5.5 2.3.5 2.8 0"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Ubuntu's circle-of-friends. */
export function UbuntuIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="12" cy="5.6" r="2.1" fill="currentColor" />
      <circle cx="6.5" cy="15.2" r="2.1" fill="currentColor" />
      <circle cx="17.5" cy="15.2" r="2.1" fill="currentColor" />
    </svg>
  );
}

/** Debian's swirl. */
export function DebianIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path
        d="M15.6 6.4a6.6 6.6 0 1 0-2.2 11.3"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <path
        d="M14.2 8.6a4 4 0 1 0-1.4 6.9"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="0.9" opacity="0.35" />
    </svg>
  );
}

/** Red Hat family — the hat, flattened. */
export function RhelIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path
        d="M4 14.6c0-1.6 1.6-2.6 3.4-3.4 1.9-.9 3.3-1.9 5.2-1.9 1.6 0 2.4.8 2.4 2 0 .5-.1.9-.2 1.2 1.6.3 2.9.8 3.7 1.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M3.9 14.6c0 2.3 4 4.1 9 4.1 3.6 0 6.7-.9 8.1-2.2.4-.4.6-.9.4-1.4l-.6-2"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M9.6 8.2c.3-1.4 1.3-2.6 2.7-2.6 1.2 0 1.9.7 2.3 1.6"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Alpine — the mountain. */
export function AlpineIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path
        d="M2.8 18.5 9 7.5l3.1 5.4 1.6-2.6 4.9 8.2H2.8Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path d="M9 7.5 12.1 12.9" stroke="currentColor" strokeWidth="1.2" opacity="0.5" />
    </svg>
  );
}

/** SUSE — the chameleon, as a simple head profile. */
export function SuseIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path
        d="M3.5 13.2c0-2.6 2.6-4.6 6.2-4.6 2.4 0 4 .7 5.6 1.6 1.3.8 2.3 1.1 3.4 1.1h1.8c-.2 3.9-3.6 6.9-8.4 6.9-5 0-8.6-2.3-8.6-5Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <circle cx="16.9" cy="10" r="1.05" fill="currentColor" />
    </svg>
  );
}

/** Arch — the peak. */
export function ArchIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path
        d="M12 3 3.5 19.5c2.6-1 4.3-2 5.4-3.1M12 3l8.5 16.5c-2.6-1-4.3-2-5.4-3.1M9 16.4c1-1 1.6-2.3 3-2.3s2 1.3 3 2.3"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const DISTRO_ICONS: Record<DistroKey, (p: IconProps) => React.ReactElement> = {
  ubuntu: UbuntuIcon,
  debian: DebianIcon,
  rhel: RhelIcon,
  alpine: AlpineIcon,
  suse: SuseIcon,
  arch: ArchIcon,
  linux: LinuxIcon,
};

/**
 * The right mark for a device: the vendor's for network gear, the distro's
 * for a server. Falls back to a generic Tux before the first successful
 * connection, when `os_family` has not been discovered yet.
 */
export function VendorIcon({
  vendor,
  deviceClass,
  osFamily,
  osVersion,
  ...props
}: IconProps & {
  vendor: string;
  deviceClass?: "network" | "server";
  osFamily?: string | null;
  osVersion?: string | null;
}) {
  if (deviceClass === "server" || vendor === "linux") {
    const Icon = DISTRO_ICONS[distroKey(osFamily, osVersion)];
    return <Icon {...props} />;
  }
  if (vendor === "mikrotik") return <MikrotikIcon {...props} />;
  return <RouterIcon {...props} />;
}

/** Generic network device, for vendors without a mark of their own yet. */
export function RouterIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <rect
        x="2.5"
        y="10.5"
        width="19"
        height="9"
        rx="2"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <circle cx="7" cy="15" r="1" fill="currentColor" />
      <circle cx="10.5" cy="15" r="1" fill="currentColor" />
      <path
        d="M12 8V5.5M8.5 6.2 12 3l3.5 3.2"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
