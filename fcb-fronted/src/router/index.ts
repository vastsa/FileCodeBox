import { createRouter, createWebHashHistory } from 'vue-router';

const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/Share/HomeView.vue'),
    },
    {
      path: '/send',
      name: 'send',
      component: () => import('@/views/Share/SendView.vue'),
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/Admin/AdminView.vue'),
      children:[
        {
          path: '',
          name: 'file',
          component: () => import('@/views/Admin/FileView.vue'),
        },
        {
          path: 'setting',
          name: 'setting',
          component: () => import('@/views/Admin/SettingView.vue'),
        },
        {
          path: 'about',
          name: 'about',
          component: () => import('@/views/Admin/AboutView.vue'),
        },
      ]
    }
  ],
});

export default router;
