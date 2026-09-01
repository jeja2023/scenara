import type { Component } from "vue";

import type { ApiKeyRecord } from "../../types";

export type AccessTab =
  | "foundation"
  | "identity"
  | "credentials"
  | "products"
  | "events"
  | "connection";

export interface IssuedApiKey {
  record: ApiKeyRecord;
  api_key: string;
}

export interface DisplayProduct {
  id: string;
  name: string;
  domain: string;
  summary: string;
  layer: string;
  maturity: string;
  scopes: string[];
}

export interface AccessTabDefinition {
  id: AccessTab;
  label: string;
  icon: Component;
}
