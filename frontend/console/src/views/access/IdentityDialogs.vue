<script setup lang="ts">
import {
  Building2,
  Check,
  FolderGit2,
  KeyRound,
  Plus,
  Shield,
  UserCheck,
  UserPlus,
  Users,
} from "@lucide/vue";

import type { Role } from "../../types";
import type {
  DisplayProduct,
  MembershipForm,
  OrganizationForm,
  PrincipalCandidate,
  ProjectForm,
  RoleForm,
  ScopePreset,
  UserForm,
} from "./types";

const {
  roles,
  principalCandidateOptions,
  scopePresets,
  productList,
  mutating,
  createOrganization,
  createProject,
  createUser,
  createMembership,
  createRole,
} = defineProps<{
  roles: Role[];
  principalCandidateOptions: PrincipalCandidate[];
  scopePresets: ScopePreset[];
  productList: DisplayProduct[];
  mutating: boolean;
  createOrganization: () => void | Promise<void>;
  createProject: () => void | Promise<void>;
  createUser: () => void | Promise<void>;
  createMembership: () => void | Promise<void>;
  createRole: () => void | Promise<void>;
}>();
const showCreateOrg = defineModel<boolean>("showCreateOrg", { required: true });
const showCreateProject = defineModel<boolean>("showCreateProject", {
  required: true,
});
const showCreateUser = defineModel<boolean>("showCreateUser", {
  required: true,
});
const showCreateMembership = defineModel<boolean>("showCreateMembership", {
  required: true,
});
const showCreateRole = defineModel<boolean>("showCreateRole", {
  required: true,
});
const organizationForm = defineModel<OrganizationForm>("organizationForm", {
  required: true,
});
const projectForm = defineModel<ProjectForm>("projectForm", { required: true });
const userForm = defineModel<UserForm>("userForm", { required: true });
const membershipForm = defineModel<MembershipForm>("membershipForm", {
  required: true,
});
const roleForm = defineModel<RoleForm>("roleForm", { required: true });

function parseList(value: string): string[] {
  return [
    ...new Set(
      value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  ];
}

function toggleMembershipRole(roleId: string): void {
  const index = membershipForm.value.role_ids.indexOf(roleId);
  if (index >= 0) membershipForm.value.role_ids.splice(index, 1);
  else membershipForm.value.role_ids.push(roleId);
}

function toggleScopePreset(scopeId: string): void {
  const scopes = parseList(roleForm.value.scopes);
  const index = scopes.indexOf(scopeId);
  if (index >= 0) scopes.splice(index, 1);
  else scopes.push(scopeId);
  roleForm.value.scopes = scopes.join(", ");
}

function toggleRoleProduct(productId: string): void {
  const index = roleForm.value.product_ids.indexOf(productId);
  if (index >= 0) roleForm.value.product_ids.splice(index, 1);
  else roleForm.value.product_ids.push(productId);
}

function selectAllRoleProducts(): void {
  roleForm.value.product_ids = productList.map((item) => item.id);
}

function clearRoleProducts(): void {
  roleForm.value.product_ids = [];
}
</script>

<template>
  <!-- ==================== 模态弹窗 1：新建组织 ==================== -->
  <div
    v-if="showCreateOrg"
    class="modal-overlay"
    @click.self="showCreateOrg = false"
  >
    <div class="modal-dialog modal-dialog-md" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div class="modal-title-box">
          <Building2 :size="17" class="modal-title-icon" />
          <div>
            <h3>新建组织租户</h3>
            <p>创建顶层多租户隔离组织边界</p>
          </div>
        </div>
      </div>
      <form @submit.prevent="createOrganization">
        <div class="modal-body">
          <label class="form-field">
            <span class="field-label"
              >组织显示名称 <em class="required">*</em></span
            >
            <input
              v-model="organizationForm.display_name"
              placeholder="例如: Scenara 华东研发中心"
              class="field-input"
              autofocus
            />
          </label>
        </div>
        <div class="modal-actions">
          <button
            type="button"
            class="button secondary tiny-btn"
            @click="showCreateOrg = false"
          >
            取消
          </button>
          <button
            type="submit"
            class="button primary tiny-btn"
            :disabled="mutating || !organizationForm.display_name.trim()"
          >
            <Plus :size="13" />确认创建组织
          </button>
        </div>
      </form>
    </div>
  </div>

  <!-- ==================== 模态弹窗 2：新建项目 ==================== -->
  <div
    v-if="showCreateProject"
    class="modal-overlay"
    @click.self="showCreateProject = false"
  >
    <div class="modal-dialog modal-dialog-md" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div class="modal-title-box">
          <FolderGit2 :size="17" class="modal-title-icon" />
          <div>
            <h3>创建新多租户项目</h3>
            <p>在当前组织下创建业务工作空间与资源容器</p>
          </div>
        </div>
      </div>
      <form @submit.prevent="createProject">
        <div class="modal-body">
          <div class="form-grid-2col">
            <label class="form-field">
              <span class="field-label"
                >项目标识 (英文) <em class="required">*</em></span
              >
              <input
                v-model="projectForm.project_id"
                placeholder="例如: smart-campus"
                class="field-input mono"
              />
            </label>
            <label class="form-field">
              <span class="field-label"
                >显示名称 <em class="required">*</em></span
              >
              <input
                v-model="projectForm.display_name"
                placeholder="例如: 智慧园区视觉系统"
                class="field-input"
              />
            </label>
          </div>
        </div>
        <div class="modal-actions">
          <button
            type="button"
            class="button secondary tiny-btn"
            @click="showCreateProject = false"
          >
            取消
          </button>
          <button
            type="submit"
            class="button primary tiny-btn"
            :disabled="
              mutating ||
              !projectForm.project_id.trim() ||
              !projectForm.display_name.trim()
            "
          >
            <Plus :size="13" />确认创建项目
          </button>
        </div>
      </form>
    </div>
  </div>

  <!-- ==================== 模态弹窗 3：新建用户 ==================== -->
  <div
    v-if="showCreateUser"
    class="modal-overlay"
    @click.self="showCreateUser = false"
  >
    <div class="modal-dialog modal-dialog-md" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div class="modal-title-box">
          <Users :size="17" class="modal-title-icon" />
          <div>
            <h3>开通新用户账号</h3>
            <p>创建租户下用于登录与权限分配的用户账号</p>
          </div>
        </div>
      </div>
      <form @submit.prevent="createUser">
        <div class="modal-body">
          <div class="form-grid-2col">
            <label class="form-field">
              <span class="field-label"
                >用户名
                <small class="muted">(登录账号，留空自动生成)</small></span
              >
              <input
                v-model="userForm.user_id"
                placeholder="如 operator-01"
                class="field-input mono"
              />
            </label>
            <label class="form-field">
              <span class="field-label"
                >显示名称 <em class="required">* (姓名或昵称)</em></span
              >
              <input
                v-model="userForm.display_name"
                placeholder="如 张三 / 运维工程师"
                class="field-input"
              />
            </label>
          </div>
          <div class="form-grid-2col">
            <label class="form-field">
              <span class="field-label">手机号码</span>
              <input
                v-model="userForm.phone"
                type="tel"
                placeholder="如 13800138000"
                class="field-input"
              />
            </label>
            <label class="form-field">
              <span class="field-label"
                >初始密码 <em class="required">* (至少8位)</em></span
              >
              <input
                v-model="userForm.password"
                type="password"
                autocomplete="new-password"
                placeholder="输入安全初始密码"
                class="field-input"
              />
            </label>
          </div>
        </div>
        <div class="modal-actions">
          <button
            type="button"
            class="button secondary tiny-btn"
            @click="showCreateUser = false"
          >
            取消
          </button>
          <button
            type="submit"
            class="button primary tiny-btn"
            :disabled="
              mutating ||
              !userForm.display_name.trim() ||
              userForm.password.length < 8
            "
          >
            <UserPlus :size="13" />确认创建用户
          </button>
        </div>
      </form>
    </div>
  </div>

  <!-- ==================== 模态弹窗 4：项目成员与角色配置 ==================== -->
  <div
    v-if="showCreateMembership"
    class="modal-overlay"
    @click.self="showCreateMembership = false"
  >
    <div class="modal-dialog modal-dialog-md" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div class="modal-title-box">
          <UserCheck :size="17" class="modal-title-icon" />
          <div>
            <h3>向当前项目分配成员与角色</h3>
            <p>绑定用户或服务账号至当前项目并授予角色权限</p>
          </div>
        </div>
      </div>
      <form @submit.prevent="createMembership">
        <div class="modal-body">
          <div class="form-grid-2col">
            <div class="form-field">
              <span class="field-label">主体类型</span>
              <div class="segmented-control">
                <button
                  type="button"
                  class="seg-btn"
                  :class="{
                    active: membershipForm.principal_type === 'user',
                  }"
                  @click="membershipForm.principal_type = 'user'"
                >
                  <Users :size="13" /> 用户
                </button>
                <button
                  type="button"
                  class="seg-btn"
                  :class="{
                    active: membershipForm.principal_type === 'service_account',
                  }"
                  @click="membershipForm.principal_type = 'service_account'"
                >
                  <KeyRound :size="13" /> 服务账号
                </button>
              </div>
            </div>

            <label class="form-field">
              <span class="field-label"
                >选择主体标识 <em class="required">*</em></span
              >
              <select v-model="membershipForm.principal_id" class="field-input">
                <option value="" disabled>
                  请选择{{
                    membershipForm.principal_type === "user"
                      ? "用户"
                      : "服务账号"
                  }}
                </option>
                <option
                  v-for="opt in principalCandidateOptions"
                  :key="opt.id"
                  :value="opt.id"
                >
                  {{ opt.name }} ({{ opt.id }})
                </option>
              </select>
            </label>
          </div>

          <!-- 分配角色多选药丸 -->
          <div class="form-field">
            <span class="field-label"
              >分配角色 (可多选) <em class="required">*</em></span
            >
            <div class="role-selection-pills">
              <button
                v-for="role in roles"
                :key="role.role_id"
                type="button"
                class="role-select-pill"
                :class="{
                  active: membershipForm.role_ids.includes(role.role_id),
                }"
                @click="toggleMembershipRole(role.role_id)"
              >
                <Check
                  v-if="membershipForm.role_ids.includes(role.role_id)"
                  :size="12"
                />
                <Shield v-else :size="12" />
                <span>{{ role.display_name }}</span>
              </button>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button
            type="button"
            class="button secondary tiny-btn"
            @click="showCreateMembership = false"
          >
            取消
          </button>
          <button
            type="submit"
            class="button primary tiny-btn"
            :disabled="
              mutating ||
              !membershipForm.principal_id ||
              !membershipForm.role_ids.length
            "
          >
            <Plus :size="13" />确认保存成员
          </button>
        </div>
      </form>
    </div>
  </div>

  <!-- ==================== 模态弹窗 5：新建角色与权限 ==================== -->
  <div
    v-if="showCreateRole"
    class="modal-overlay"
    @click.self="showCreateRole = false"
  >
    <div class="modal-dialog modal-dialog-lg" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div class="modal-title-box">
          <Shield :size="17" class="modal-title-icon" />
          <div>
            <h3>定义新安全角色与权限</h3>
            <p>自定义角色权限范围及适用产品授权</p>
          </div>
        </div>
      </div>
      <form @submit.prevent="createRole">
        <div class="modal-body">
          <div class="form-grid-2col">
            <label class="form-field">
              <span class="field-label"
                >角色标识
                <small class="muted">(英文标识，留空自动生成)</small></span
              >
              <input
                v-model="roleForm.role_id"
                placeholder="例如: role:operator"
                class="field-input mono"
              />
            </label>
            <label class="form-field">
              <span class="field-label"
                >角色显示名称 <em class="required">* (中文名称)</em></span
              >
              <input
                v-model="roleForm.display_name"
                placeholder="例如: 运维操作员 / 视觉审计员"
                class="field-input"
              />
            </label>
          </div>

          <!-- 权限范围选择 -->
          <div class="form-field">
            <span class="field-label"
              >权限范围
              <em class="required">* (可点击上方快捷预设或手动输入)</em></span
            >
            <div class="scope-presets-row">
              <button
                v-for="preset in scopePresets"
                :key="preset.id"
                type="button"
                class="preset-chip"
                :class="{
                  active: parseList(roleForm.scopes).includes(preset.id),
                }"
                :title="preset.summary"
                @click="toggleScopePreset(preset.id)"
              >
                <Check
                  v-if="parseList(roleForm.scopes).includes(preset.id)"
                  :size="11"
                />
                <span>{{ preset.label }}</span>
              </button>
            </div>
            <input
              v-model="roleForm.scopes"
              class="field-input mono scope-input"
              placeholder="支持逗号分隔多个权限标识，例如: iam:read, media_asset:create"
            />
          </div>

          <!-- 适用产品标签多选选择器 -->
          <div class="form-field">
            <div class="field-label-row">
              <span class="field-label"
                >适用产品范围
                <small class="muted"
                  >(可多选，留空默认全部产品可用)</small
                ></span
              >
              <div class="chips-quick-actions">
                <button
                  type="button"
                  class="link-btn"
                  @click="selectAllRoleProducts"
                >
                  全选
                </button>
                <span class="divider">|</span>
                <button
                  type="button"
                  class="link-btn"
                  @click="clearRoleProducts"
                >
                  清空
                </button>
              </div>
            </div>
            <div class="product-chips-grid">
              <button
                v-for="prod in productList"
                :key="prod.id"
                type="button"
                class="product-chip"
                :class="{ active: roleForm.product_ids.includes(prod.id) }"
                @click="toggleRoleProduct(prod.id)"
              >
                <div class="chip-check">
                  <Check
                    v-if="roleForm.product_ids.includes(prod.id)"
                    :size="12"
                  />
                </div>
                <div class="chip-text">
                  <strong>{{ prod.name }}</strong>
                  <small>{{ prod.domain }}</small>
                </div>
              </button>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button
            type="button"
            class="button secondary tiny-btn"
            @click="showCreateRole = false"
          >
            取消
          </button>
          <button
            type="submit"
            class="button primary tiny-btn"
            :disabled="
              mutating ||
              !roleForm.display_name.trim() ||
              !parseList(roleForm.scopes).length
            "
          >
            <Plus :size="13" />确认创建角色
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
