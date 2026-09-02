import type { Component } from "vue";

import type { ApiKeyRecord } from "../../types";

export type AccessTab =
  "foundation" | "identity" | "credentials" | "products" | "events";

export type IdentitySubTab =
  "organizations" | "projects" | "users" | "memberships" | "roles";

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

export interface OrganizationForm {
  display_name: string;
}

export interface ProjectForm {
  project_id: string;
  display_name: string;
}

export interface UserForm {
  user_id: string;
  display_name: string;
  phone: string;
  email: string;
  password: string;
}

export interface MembershipForm {
  principal_id: string;
  principal_type: "user" | "service_account";
  role_ids: string[];
}

export interface RoleForm {
  role_id: string;
  display_name: string;
  scopes: string;
  product_ids: string[];
}

export interface ServiceAccountForm {
  service_account_id: string;
  display_name: string;
  scopes: string;
  product_ids: string[];
}

export interface ApiKeyForm {
  service_account_id: string;
  name: string;
  scopes: string;
  product_ids: string[];
  expires_at: string;
}

export interface EntitlementForm {
  product_id: string;
  status: "active" | "suspended";
}

export interface WebhookForm {
  name: string;
  url: string;
  secret: string;
  event_types: string[];
}

export interface ScopePreset {
  id: string;
  label: string;
  summary: string;
}

export interface PrincipalCandidate {
  id: string;
  name: string;
  detail: string;
}
