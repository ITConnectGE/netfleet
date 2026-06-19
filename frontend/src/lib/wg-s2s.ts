import { api, readErrorMessage } from "@/lib/api";

export interface S2SSide {
  device_id: string;
  interface_name: string;
  tunnel_cidr: string;
  expose_subnets: string[];
}

export interface S2SCreateRequest {
  a: S2SSide;
  b: S2SSide;
  listen_port: number;
  public_endpoint: string;
  comment_tag: string;
  open_firewall_on_a: boolean;
  create_forward_rules: boolean;
  create_routes: boolean;
  persistent_keepalive: number;
}

export interface S2SCreatedArtifact {
  side: "a" | "b";
  kind: "interface" | "address" | "peer" | "filter" | "route";
  id: string | null;
  detail: string | null;
}

export interface S2SCreateResponse {
  comment_tag: string;
  artifacts: S2SCreatedArtifact[];
  public_key_a: string;
  public_key_b: string;
}

export async function createSiteToSite(
  payload: S2SCreateRequest,
): Promise<S2SCreateResponse> {
  try {
    return await api
      .post("wireguard-tunnels/site-to-site", { json: payload })
      .json<S2SCreateResponse>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
