import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('../components/layout/AppShell.vue'),
    children: [
      { path: '', name: 'dashboard', component: () => import('../views/DashboardView.vue') },
      { path: 'hosts', name: 'hosts', component: () => import('../views/hosts/HostsView.vue') },
      { path: 'apps', name: 'apps', component: () => import('../views/apps/AppsListView.vue') },
      { path: 'apps/:id', name: 'app-detail', component: () => import('../views/apps/AppDetailView.vue') },
      { path: 'github', name: 'github', component: () => import('../views/github/GithubView.vue') },
      { path: 'traffic', name: 'traffic', component: () => import('../views/traffic/TrafficView.vue') },
      { path: 'deployments', name: 'deployments', component: () => import('../views/deployments/DeploymentsView.vue') },
      { path: 'backups', name: 'backups', component: () => import('../views/backups/BackupsView.vue') },
      { path: 'secrets', name: 'secrets', component: () => import('../views/secrets/SecretsView.vue') },
      { path: 'audit', name: 'audit', component: () => import('../views/audit/AuditView.vue') },
      { path: 'mcp', name: 'mcp', component: () => import('../views/mcp/McpView.vue') },
      { path: 'settings', name: 'settings', component: () => import('../views/settings/SettingsView.vue') },
    ],
  },
  // Cockpit, Kanban, Kompaktansicht und LLM-Konsole laufen ohne Sidebar (Vollbild), aber mit Anmeldung.
  { path: '/board', name: 'board', component: () => import('../views/WallView.vue') },
  // Alter Pfad: Lesezeichen, Desktop-Verknüpfungen und das SwiftBar-Menü zeigen noch auf /wall.
  { path: '/wall', redirect: '/board' },
  { path: '/kanban', name: 'kanban', component: () => import('../views/KanbanView.vue') },
  { path: '/kompakt', name: 'kompakt', component: () => import('../views/KompaktView.vue') },
  { path: '/chat', name: 'chat', component: () => import('../views/ChatView.vue') },
  { path: '/ki', redirect: '/kanban' },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory('/admin/'),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  auth.hydrate()
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  if (to.name === 'login' && auth.isAuthenticated) {
    return { name: 'dashboard' }
  }
})

export default router
