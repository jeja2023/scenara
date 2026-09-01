<script setup lang="ts">
import {
  Building2,
  Check,
  Clipboard,
  FolderGit2,
  Phone,
  Plus,
  Search,
  Shield,
  UserCheck,
  Users,
  X,
} from "@lucide/vue";

import DataTablePagination from "../../components/DataTablePagination.vue";
import { labelProduct, labelScope } from "../../labels";
import type {
  Membership,
  Organization,
  Project,
  Role,
  UserAccount,
} from "../../types";
import type { IdentitySubTab } from "./types";

const {
  organizations,
  projects,
  users,
  roles,
  memberships,
  filteredOrganizations,
  filteredProjects,
  filteredUsers,
  filteredMemberships,
  filteredRoles,
  paginatedOrganizations,
  paginatedProjects,
  paginatedUsers,
  paginatedMemberships,
  paginatedRoles,
  activeUsersCount,
  disabledUsersCount,
  userRolesMap,
  copiedKey,
  copyToClipboard,
  openAssignRole,
  getPrincipalDisplayName,
  getRoleMemberCount,
  formatTime,
} = defineProps<{
  organizations: Organization[];
  projects: Project[];
  users: UserAccount[];
  roles: Role[];
  memberships: Membership[];
  filteredOrganizations: Organization[];
  filteredProjects: Project[];
  filteredUsers: UserAccount[];
  filteredMemberships: Membership[];
  filteredRoles: Role[];
  paginatedOrganizations: Organization[];
  paginatedProjects: Project[];
  paginatedUsers: UserAccount[];
  paginatedMemberships: Membership[];
  paginatedRoles: Role[];
  activeUsersCount: number;
  disabledUsersCount: number;
  userRolesMap: Map<string, Role[]>;
  copiedKey: string | null;
  copyToClipboard: (value: string, key: string) => void | Promise<void>;
  openAssignRole: (userId: string) => void;
  getPrincipalDisplayName: (
    principalId: string,
    principalType: "user" | "service_account",
  ) => string;
  getRoleMemberCount: (roleId: string) => number;
  formatTime: (value?: number | null) => string;
}>();
const emit = defineEmits<{
  (event: "open-organization"): void;
  (event: "open-project"): void;
  (event: "open-user"): void;
  (event: "open-role"): void;
  (
    event: "open-membership",
    principalType?: "user" | "service_account",
    principalId?: string,
    roleIds?: string[],
  ): void;
}>();
const identitySubTab = defineModel<IdentitySubTab>("identitySubTab", {
  required: true,
});
const orgSearch = defineModel<string>("orgSearch", { required: true });
const projectSearch = defineModel<string>("projectSearch", { required: true });
const userSearch = defineModel<string>("userSearch", { required: true });
const userStatusFilter = defineModel<"all" | "active" | "disabled">(
  "userStatusFilter",
  { required: true },
);
const memberSearch = defineModel<string>("memberSearch", { required: true });
const roleSearch = defineModel<string>("roleSearch", { required: true });
const orgsPagination = defineModel<{ offset: number; pageSize: number }>(
  "orgsPagination",
  { required: true },
);
const projectsPagination = defineModel<{ offset: number; pageSize: number }>(
  "projectsPagination",
  { required: true },
);
const usersPagination = defineModel<{ offset: number; pageSize: number }>(
  "usersPagination",
  { required: true },
);
const membershipsPagination = defineModel<{ offset: number; pageSize: number }>(
  "membershipsPagination",
  { required: true },
);
const rolesPagination = defineModel<{ offset: number; pageSize: number }>(
  "rolesPagination",
  { required: true },
);
</script>

<template>
  <!-- 统一的子模块 Tab 切换栏 -->
  <div class="tabs-header-bar subtabs-bar">
    <div class="domain-tabs" role="tablist" aria-label="成员与角色子视图">
      <button
        type="button"
        class="domain-tab-btn"
        :class="{ active: identitySubTab === 'organizations' }"
        @click="identitySubTab = 'organizations'"
      >
        <Building2 :size="13" />
        <span>组织</span>
        <span class="tab-badge">{{ organizations.length }}</span>
      </button>
      <button
        type="button"
        class="domain-tab-btn"
        :class="{ active: identitySubTab === 'projects' }"
        @click="identitySubTab = 'projects'"
      >
        <FolderGit2 :size="13" />
        <span>项目</span>
        <span class="tab-badge">{{ projects.length }}</span>
      </button>
      <button
        type="button"
        class="domain-tab-btn"
        :class="{ active: identitySubTab === 'users' }"
        @click="identitySubTab = 'users'"
      >
        <Users :size="13" />
        <span>用户管理</span>
        <span class="tab-badge">{{ users.length }}</span>
      </button>
      <button
        type="button"
        class="domain-tab-btn"
        :class="{ active: identitySubTab === 'memberships' }"
        @click="identitySubTab = 'memberships'"
      >
        <UserCheck :size="13" />
        <span>项目成员</span>
        <span class="tab-badge">{{ memberships.length }}</span>
      </button>
      <button
        type="button"
        class="domain-tab-btn"
        :class="{ active: identitySubTab === 'roles' }"
        @click="identitySubTab = 'roles'"
      >
        <Shield :size="13" />
        <span>角色与权限</span>
        <span class="tab-badge">{{ roles.length }}</span>
      </button>
    </div>
  </div>

  <!-- 子视图 1：组织 (Organizations) -->
  <section v-if="identitySubTab === 'organizations'" class="panel">
    <div class="panel-header">
      <div class="header-left">
        <Building2 :size="16" class="header-icon" />
        <h2>组织</h2>
        <span class="badge">{{ organizations.length }}</span>
      </div>
      <div class="header-actions">
        <div class="search-box">
          <Search :size="13" class="search-icon" />
          <input
            v-model="orgSearch"
            placeholder="搜索组织名称 / 租户标识..."
            class="search-input"
          />
          <button
            v-if="orgSearch"
            class="clear-search-btn"
            @click="orgSearch = ''"
          >
            <X :size="12" />
          </button>
        </div>
        <button
          class="button primary tiny-btn"
          @click="emit('open-organization')"
        >
          <Plus :size="13" />新建组织
        </button>
      </div>
    </div>

    <div class="table-scroll">
      <table class="data-table iam-table">
        <thead>
          <tr>
            <th style="width: 48px; text-align: center">序号</th>
            <th style="min-width: 160px">组织名称</th>
            <th style="min-width: 140px">租户标识</th>
            <th style="width: 100px; text-align: center">租户类型</th>
            <th style="width: 150px">创建时间</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(item, index) in paginatedOrganizations"
            :key="item.tenant_id"
          >
            <td class="muted text-center">
              {{ index + 1 + orgsPagination.offset }}
            </td>
            <td>
              <strong>{{ item.display_name }}</strong>
            </td>
            <td class="mono muted-id">{{ item.tenant_id }}</td>
            <td class="text-center">
              <span
                class="badge"
                :class="
                  item.tenant_id === 'default' ? 'primary-soft' : 'ghost-badge'
                "
              >
                {{ item.tenant_id === "default" ? "默认租户" : "自定义租户" }}
              </span>
            </td>
            <td class="muted">{{ formatTime(item.created_at) }}</td>
          </tr>
          <tr v-if="!filteredOrganizations.length">
            <td colspan="5" class="empty">
              {{
                organizations.length ? "未找到符合条件的组织" : "暂无组织信息"
              }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <DataTablePagination
      v-if="filteredOrganizations.length"
      :total="filteredOrganizations.length"
      :offset="orgsPagination.offset"
      :page-size="orgsPagination.pageSize"
      :page-size-options="[10, 20, 50]"
      @update:offset="orgsPagination.offset = $event"
      @update:page-size="orgsPagination.pageSize = $event"
    />
  </section>

  <!-- 子视图 2：项目 (Projects) -->
  <section v-else-if="identitySubTab === 'projects'" class="panel">
    <div class="panel-header">
      <div class="header-left">
        <FolderGit2 :size="16" class="header-icon" />
        <h2>项目</h2>
        <span class="badge">{{ projects.length }}</span>
      </div>
      <div class="header-actions">
        <div class="search-box">
          <Search :size="13" class="search-icon" />
          <input
            v-model="projectSearch"
            placeholder="搜索项目名称 / 项目标识..."
            class="search-input"
          />
          <button
            v-if="projectSearch"
            class="clear-search-btn"
            @click="projectSearch = ''"
          >
            <X :size="12" />
          </button>
        </div>
        <button class="button primary tiny-btn" @click="emit('open-project')">
          <Plus :size="13" />新建项目
        </button>
      </div>
    </div>

    <div class="table-scroll">
      <table class="data-table iam-table">
        <thead>
          <tr>
            <th style="width: 48px; text-align: center">序号</th>
            <th style="min-width: 160px">项目名称</th>
            <th style="min-width: 140px">项目标识</th>
            <th style="min-width: 120px">所属租户</th>
            <th style="width: 150px">创建时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in paginatedProjects" :key="item.project_id">
            <td class="muted text-center">
              {{ index + 1 + projectsPagination.offset }}
            </td>
            <td>
              <strong>{{ item.display_name }}</strong>
              <span
                v-if="item.project_id === 'default'"
                class="badge primary-soft"
                style="margin-left: 6px"
                >默认项目</span
              >
            </td>
            <td class="mono muted-id">{{ item.project_id }}</td>
            <td class="mono muted">{{ item.tenant_id }}</td>
            <td class="muted">{{ formatTime(item.created_at) }}</td>
          </tr>
          <tr v-if="!filteredProjects.length">
            <td colspan="5" class="empty">
              {{ projects.length ? "未找到符合条件的项目" : "暂无项目" }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <DataTablePagination
      v-if="filteredProjects.length"
      :total="filteredProjects.length"
      :offset="projectsPagination.offset"
      :page-size="projectsPagination.pageSize"
      :page-size-options="[10, 20, 50]"
      @update:offset="projectsPagination.offset = $event"
      @update:page-size="projectsPagination.pageSize = $event"
    />
  </section>

  <!-- 子视图 3：用户管理 (Users) -->
  <section v-else-if="identitySubTab === 'users'" class="panel">
    <div class="panel-header">
      <div class="header-left">
        <Users :size="16" class="header-icon" />
        <h2>用户</h2>
        <span class="badge">{{ users.length }}</span>
        <div class="header-sub-stats">
          <span class="sub-stat-dot active"></span>
          <span class="sub-stat-text">{{ activeUsersCount }} 启用</span>
          <span v-if="disabledUsersCount" class="sub-stat-dot disabled"></span>
          <span v-if="disabledUsersCount" class="sub-stat-text muted"
            >{{ disabledUsersCount }} 停用</span
          >
        </div>
      </div>
      <div class="header-actions">
        <!-- 快速搜索与筛选 -->
        <div class="search-box">
          <Search :size="13" class="search-icon" />
          <input
            v-model="userSearch"
            placeholder="搜索用户名 / 显示名称 / 手机号码..."
            class="search-input"
          />
          <button
            v-if="userSearch"
            class="clear-search-btn"
            @click="userSearch = ''"
          >
            <X :size="12" />
          </button>
        </div>
        <select v-model="userStatusFilter" class="filter-select-sm">
          <option value="all">全部状态 ({{ users.length }})</option>
          <option value="active">仅启用 ({{ activeUsersCount }})</option>
          <option value="disabled">仅停用 ({{ disabledUsersCount }})</option>
        </select>
        <button class="button primary tiny-btn" @click="emit('open-user')">
          <Plus :size="13" />新建用户
        </button>
      </div>
    </div>

    <!-- 用户表格 -->
    <div class="table-scroll">
      <table class="data-table iam-table">
        <thead>
          <tr>
            <th style="width: 48px; text-align: center">序号</th>
            <th style="min-width: 140px">用户名</th>
            <th style="min-width: 140px">显示名称</th>
            <th style="min-width: 130px">手机号码</th>
            <th style="min-width: 180px">项目已授角色</th>
            <th style="width: 90px; text-align: center">账号状态</th>
            <th style="width: 150px">注册时间</th>
            <th style="width: 80px; text-align: center">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in paginatedUsers" :key="item.user_id">
            <td class="muted text-center">
              {{ index + 1 + usersPagination.offset }}
            </td>
            <td>
              <div class="user-id-chip-row">
                <strong class="mono">{{ item.user_id }}</strong>
                <button
                  type="button"
                  class="copy-mini-btn"
                  :title="copiedKey === item.user_id ? '已复制' : '复制用户名'"
                  @click="copyToClipboard(item.user_id, item.user_id)"
                >
                  <Check
                    v-if="copiedKey === item.user_id"
                    :size="10"
                    class="copied-check"
                  />
                  <Clipboard v-else :size="10" />
                </button>
              </div>
            </td>
            <td>
              <span>{{ item.display_name || item.user_id }}</span>
            </td>
            <td>
              <div v-if="item.phone || item.email" class="phone-cell">
                <Phone :size="12" class="muted-icon" />
                <span>{{ item.phone || item.email }}</span>
              </div>
              <span v-else class="muted">-</span>
            </td>
            <td>
              <div class="role-tags-cell">
                <span
                  v-for="role in userRolesMap.get(item.user_id) || []"
                  :key="role.role_id"
                  class="badge role-pill"
                  :title="role.scopes.map(labelScope).join('、')"
                >
                  <Shield :size="10" />
                  {{ role.display_name }}
                </span>
                <button
                  v-if="!userRolesMap.get(item.user_id)?.length"
                  type="button"
                  class="assign-role-btn-link"
                  title="为该用户分配项目角色"
                  @click="openAssignRole(item.user_id)"
                >
                  <Plus :size="10" />分配角色
                </button>
              </div>
            </td>
            <td class="text-center">
              <span
                class="badge status-pill"
                :class="item.disabled ? 'failed' : 'active'"
              >
                <span class="status-dot"></span>
                {{ item.disabled ? "停用" : "启用" }}
              </span>
            </td>
            <td class="muted">{{ formatTime(item.created_at) }}</td>
            <td class="text-center">
              <button
                type="button"
                class="button secondary tiny-btn"
                title="配置项目角色"
                @click="openAssignRole(item.user_id)"
              >
                <Shield :size="11" />角色
              </button>
            </td>
          </tr>
          <tr v-if="!filteredUsers.length">
            <td colspan="8" class="empty">
              {{ users.length ? "未找到符合条件的用户" : "暂无用户" }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <DataTablePagination
      v-if="filteredUsers.length"
      :total="filteredUsers.length"
      :offset="usersPagination.offset"
      :page-size="usersPagination.pageSize"
      :page-size-options="[10, 20, 50, 100]"
      @update:offset="usersPagination.offset = $event"
      @update:page-size="usersPagination.pageSize = $event"
    />
  </section>

  <!-- 子视图 3：项目成员 (Memberships) -->
  <section v-else-if="identitySubTab === 'memberships'" class="panel">
    <div class="panel-header">
      <div class="header-left">
        <UserCheck :size="16" class="header-icon" />
        <h2>项目成员</h2>
        <span class="badge">{{ memberships.length }}</span>
      </div>
      <div class="header-actions">
        <!-- 搜索框 -->
        <div class="search-box">
          <Search :size="13" class="search-icon" />
          <input
            v-model="memberSearch"
            placeholder="搜索成员主体标识 / 角色..."
            class="search-input"
          />
          <button
            v-if="memberSearch"
            class="clear-search-btn"
            @click="memberSearch = ''"
          >
            <X :size="12" />
          </button>
        </div>
        <button
          class="button primary tiny-btn"
          @click="emit('open-membership')"
        >
          <Plus :size="13" />添加成员
        </button>
      </div>
    </div>

    <!-- 成员表格 -->
    <div class="table-scroll">
      <table class="data-table iam-table">
        <thead>
          <tr>
            <th style="width: 48px; text-align: center">序号</th>
            <th style="min-width: 160px">成员主体</th>
            <th style="width: 90px; text-align: center">主体类型</th>
            <th style="min-width: 140px">主体标识</th>
            <th style="min-width: 200px">项目已授角色</th>
            <th style="width: 80px; text-align: center">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(item, index) in paginatedMemberships"
            :key="item.principal_id"
          >
            <td class="muted text-center">
              {{ index + 1 + membershipsPagination.offset }}
            </td>
            <td>
              <strong>{{
                getPrincipalDisplayName(item.principal_id, item.principal_type)
              }}</strong>
            </td>
            <td class="text-center">
              <span class="badge type-badge" :class="item.principal_type">
                {{ item.principal_type === "user" ? "用户" : "服务账号" }}
              </span>
            </td>
            <td class="mono muted-id">{{ item.principal_id }}</td>
            <td>
              <div class="role-tags-cell">
                <span
                  v-for="roleId in item.role_ids"
                  :key="roleId"
                  class="badge role-pill"
                >
                  <Shield :size="10" />
                  {{
                    roles.find((r) => r.role_id === roleId)?.display_name ||
                    roleId
                  }}
                </span>
              </div>
            </td>
            <td class="text-center">
              <button
                type="button"
                class="button secondary tiny-btn"
                title="配置成员角色"
                @click="
                  emit(
                    'open-membership',
                    item.principal_type,
                    item.principal_id,
                    item.role_ids,
                  )
                "
              >
                <Shield :size="11" />配置
              </button>
            </td>
          </tr>
          <tr v-if="!filteredMemberships.length">
            <td colspan="6" class="empty">
              {{
                memberships.length
                  ? "未找到符合条件的项目成员"
                  : "当前项目暂无成员关联"
              }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <DataTablePagination
      v-if="filteredMemberships.length"
      :total="filteredMemberships.length"
      :offset="membershipsPagination.offset"
      :page-size="membershipsPagination.pageSize"
      :page-size-options="[10, 20, 50, 100]"
      @update:offset="membershipsPagination.offset = $event"
      @update:page-size="membershipsPagination.pageSize = $event"
    />
  </section>

  <!-- 子视图 4：角色与权限 (Roles) -->
  <section v-else-if="identitySubTab === 'roles'" class="panel">
    <div class="panel-header">
      <div class="header-left">
        <Shield :size="16" class="header-icon" />
        <h2>角色</h2>
        <span class="badge">{{ roles.length }}</span>
      </div>
      <div class="header-actions">
        <!-- 搜索框 -->
        <div class="search-box">
          <Search :size="13" class="search-icon" />
          <input
            v-model="roleSearch"
            placeholder="搜索角色名 / 标识 / 权限..."
            class="search-input"
          />
          <button
            v-if="roleSearch"
            class="clear-search-btn"
            @click="roleSearch = ''"
          >
            <X :size="12" />
          </button>
        </div>
        <button class="button primary tiny-btn" @click="emit('open-role')">
          <Plus :size="13" />新建角色
        </button>
      </div>
    </div>

    <!-- 角色表格 -->
    <div class="table-scroll">
      <table class="data-table iam-table">
        <thead>
          <tr>
            <th style="width: 48px; text-align: center">序号</th>
            <th style="min-width: 140px">角色名称</th>
            <th style="min-width: 130px">角色标识</th>
            <th style="min-width: 220px">权限范围</th>
            <th style="min-width: 160px">适用产品</th>
            <th style="width: 90px; text-align: center">绑定成员数</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in paginatedRoles" :key="item.role_id">
            <td class="muted text-center">
              {{ index + 1 + rolesPagination.offset }}
            </td>
            <td>
              <strong>{{ item.display_name }}</strong>
            </td>
            <td class="mono muted-id">{{ item.role_id }}</td>
            <td>
              <div class="role-tags-cell">
                <span
                  v-for="scope in item.scopes"
                  :key="scope"
                  class="badge scope-pill"
                  :title="scope"
                >
                  {{ labelScope(scope) }}
                </span>
              </div>
            </td>
            <td>
              <div v-if="item.product_ids?.length" class="role-tags-cell">
                <span
                  v-for="pid in item.product_ids"
                  :key="pid"
                  class="badge product-pill"
                >
                  {{ labelProduct(pid) }}
                </span>
              </div>
              <span v-else class="muted">全部产品</span>
            </td>
            <td class="text-center">
              <span class="badge member-count-badge">
                {{ getRoleMemberCount(item.role_id) }} 位成员
              </span>
            </td>
          </tr>
          <tr v-if="!filteredRoles.length">
            <td colspan="6" class="empty">
              {{ roles.length ? "未找到符合条件的角色" : "暂无角色定义" }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <DataTablePagination
      v-if="filteredRoles.length"
      :total="filteredRoles.length"
      :offset="rolesPagination.offset"
      :page-size="rolesPagination.pageSize"
      :page-size-options="[10, 20, 50, 100]"
      @update:offset="rolesPagination.offset = $event"
      @update:page-size="rolesPagination.pageSize = $event"
    />
  </section>
</template>
