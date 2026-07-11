import { defineConfig } from 'vitepress'

// https://vitepress.dev/reference/site-config
export default defineConfig({
  title: 'FileCodeBox',
  description: 'FileCodeBox 自托管文件与文本分享服务文档',
  lang: 'zh-CN',
  lastUpdated: true,
  cleanUrls: true,
  sitemap: {
    hostname: 'https://fcb-docs.aiuo.net',
  },
  head: [
    ['meta', { name: 'theme-color', content: '#111111' }],
    ['link', { rel: 'icon', href: '/logo_small.png' }],
  ],
  locales: {
    root: {
      label: '简体中文',
      lang: 'zh-CN',
      title: 'FileCodeBox',
      description: '匿名口令分享文本，文件',
      themeConfig: {
        logo: '/logo_small.png',
        nav: [
          { text: '首页', link: '/' },
          {
            text: '使用指南',
            items: [
              { text: '快速开始', link: '/guide/getting-started' },
              { text: '上传与分享', link: '/guide/upload' },
              { text: '管理面板', link: '/guide/management' },
              { text: '存储配置', link: '/guide/storage' },
            ],
          },
          { text: 'API', link: '/api/' },
          {
            text: '资源',
            items: [
              { text: '在线体验', link: 'https://share.lanol.cn' },
              { text: '部署案例', link: '/showcase' },
              { text: '更新日志', link: '/changelog' },
              { text: '贡献指南', link: '/contributing' },
              { text: 'GitHub', link: 'https://github.com/vastsa/FileCodeBox' },
            ],
          },
        ],

        sidebar: {
          '/guide/': [
            {
              text: '开始',
              items: [
                {
                  text: '什么是 FileCodeBox',
                  link: '/guide/introduction',
                },
                { text: '快速开始', link: '/guide/getting-started' },
              ],
            },
            {
              text: '使用',
              items: [
                { text: '文件上传', link: '/guide/upload' },
                { text: '文件分享', link: '/guide/share' },
                { text: '文件管理', link: '/guide/management' },
              ],
            },
            {
              text: '运维',
              items: [
                { text: '存储配置', link: '/guide/storage' },
                { text: '安全设置', link: '/guide/security' },
                { text: '系统配置', link: '/guide/configuration' },
                { text: '版本发布', link: '/guide/releasing' },
              ],
            },
          ],
          '/api/': [
            {
              text: 'API 参考',
              items: [
                { text: 'API 概览', link: '/api/' },
                { text: '预签名上传', link: '/api/presign-upload' },
                { text: '分享接口', link: '/api/#分享接口' },
                { text: '管理接口', link: '/api/#管理接口' },
                { text: '错误响应', link: '/api/#错误响应' },
                { text: '状态码说明', link: '/api/#状态码说明' },
              ],
            },
          ],
          '/showcase': [
            {
              text: '优秀案例',
              items: [
                { text: '案例展示', link: '/showcase' },
              ],
            },
          ],
        },
        socialLinks: [
          { icon: 'github', link: 'https://github.com/vastsa/FileCodeBox' },
        ],
        footer: {
          message: '基于 LGPL-3.0 许可证发布',
          copyright: 'Copyright © 2022-present FileCodeBox',
        },
        editLink: {
          pattern: 'https://github.com/vastsa/FileCodeBox/edit/master/docs/:path',
          text: '在 GitHub 上编辑此页',
        },
        docFooter: {
          prev: '上一篇',
          next: '下一篇',
        },
        lastUpdated: {
          text: '最后更新',
        },
        returnToTopLabel: '返回顶部',
        skipToContentLabel: '跳转到正文',
        navMenuLabel: '导航菜单',
        langMenuLabel: '切换语言',
        sidebarMenuLabel: '文档目录',
        darkModeSwitchLabel: '外观',
        lightModeSwitchTitle: '切换到浅色模式',
        darkModeSwitchTitle: '切换到深色模式',
        search: {
          provider: 'local',
        },
        outline: {
          level: [2, 3],
          label: '目录',
        },
      },
    },
    en: {
      label: 'English',
      lang: 'en-US',
      title: 'FileCodeBox',
      description: 'Simple and efficient file sharing tool',
      themeConfig: {
        logo: '/logo_small.png',
        nav: [
          { text: 'Home', link: '/en/' },
          {
            text: 'Guides',
            items: [
              { text: 'Getting Started', link: '/en/guide/getting-started' },
              { text: 'Upload & Share', link: '/en/guide/upload' },
              { text: 'Admin Panel', link: '/en/guide/management' },
              { text: 'Storage', link: '/en/guide/storage' },
            ],
          },
          { text: 'API', link: '/en/api/' },
          {
            text: 'Resources',
            items: [
              { text: 'Live Demo', link: 'https://share.lanol.cn' },
              { text: 'Showcase', link: '/en/showcase' },
              { text: 'Changelog', link: '/en/changelog' },
              { text: 'Contributing', link: '/en/contributing' },
              { text: 'GitHub', link: 'https://github.com/vastsa/FileCodeBox' },
            ],
          },
        ],

        sidebar: {
          '/en/guide/': [
            {
              text: 'Start',
              items: [
                {
                  text: 'What is FileCodeBox',
                  link: '/en/guide/introduction',
                },
                {
                  text: 'Getting Started',
                  link: '/en/guide/getting-started',
                },
              ],
            },
            {
              text: 'Use',
              items: [
                { text: 'File Upload', link: '/en/guide/upload' },
                { text: 'File Sharing', link: '/en/guide/share' },
                { text: 'File Management', link: '/en/guide/management' },
              ],
            },
            {
              text: 'Operate',
              items: [
                { text: 'Storage Configuration', link: '/en/guide/storage' },
                { text: 'Security Settings', link: '/en/guide/security' },
                {
                  text: 'System Configuration',
                  link: '/en/guide/configuration',
                },
                { text: 'Releasing', link: '/en/guide/releasing' },
              ],
            },
          ],
          '/en/api/': [
            {
              text: 'API Reference',
              items: [
                { text: 'API Overview', link: '/en/api/' },
                { text: 'Share API', link: '/en/api/#share-api' },
                { text: 'Admin API', link: '/en/api/#admin-api' },
                { text: 'Error Response', link: '/en/api/#error-response' },
                { text: 'Status Codes', link: '/en/api/#status-codes' },
              ],
            },
          ],
          '/en/showcase': [
            {
              text: 'Showcase',
              items: [
                { text: 'Case Studies', link: '/en/showcase' },
              ],
            },
          ],
        },
        socialLinks: [
          { icon: 'github', link: 'https://github.com/vastsa/FileCodeBox' },
        ],
        footer: {
          message: 'Released under the LGPL-3.0 license',
          copyright: 'Copyright © 2022-present FileCodeBox',
        },
        editLink: {
          pattern: 'https://github.com/vastsa/FileCodeBox/edit/master/docs/:path',
          text: 'Edit this page on GitHub',
        },
        docFooter: {
          prev: 'Previous',
          next: 'Next',
        },
        lastUpdated: {
          text: 'Last updated',
        },
        returnToTopLabel: 'Return to top',
        skipToContentLabel: 'Skip to content',
        navMenuLabel: 'Navigation',
        langMenuLabel: 'Change language',
        sidebarMenuLabel: 'Documentation',
        darkModeSwitchLabel: 'Appearance',
        lightModeSwitchTitle: 'Switch to light theme',
        darkModeSwitchTitle: 'Switch to dark theme',
        search: {
          provider: 'local',
        },
        outline: {
          level: [2, 3],
          label: 'On this page',
        },
      },
    },
  },

  themeConfig: {
    // 语言切换器
    langMenuLabel: '切换语言',

    // 社交链接
    socialLinks: [
      { icon: 'github', link: 'https://github.com/vastsa/FileCodeBox' },
    ],

    // 页脚
    footer: {
      message: '基于 LGPL-3.0 license 发布',
      copyright: 'Copyright © 2022-present FileCodeBox',
    },

    // 搜索
    search: {
      provider: 'local',
      options: {
        locales: {
          zh: {
            translations: {
              button: {
                buttonText: '搜索文档',
                buttonAriaLabel: '搜索文档',
              },
              modal: {
                noResultsText: '无法找到相关结果',
                resetButtonTitle: '清除查询条件',
                footer: {
                  selectText: '选择',
                  navigateText: '切换',
                },
              },
            },
          },
          en: {
            translations: {
              button: {
                buttonText: 'Search',
                buttonAriaLabel: 'Search docs',
              },
              modal: {
                noResultsText: 'No results found',
                resetButtonTitle: 'Clear query',
                footer: {
                  selectText: 'to select',
                  navigateText: 'to navigate',
                },
              },
            },
          },
        },
      },
    },

    outline: {
      level: [2, 3],
      label: '目录',
    },
    externalLinkIcon: true,
  },
})
