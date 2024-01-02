export default {
  send: {
    mzsm:'免责声明',
    alert: '感谢您选择使用我们的文件分享服务。在您使用本网站之前，请仔细阅读以下免责条款：

数据加密: 本网站并未采用端到端加密技术。这意味着在上传或下载文件时，数据可能会在传输过程中被未经授权的第三方访问。因此，我们强烈建议您不要通过我们的服务上传或分享任何敏感、机密或个人隐私数据。
内容责任: 用户完全负责自己上传到网站上的所有内容。用户必须保证拥有或已获得合适的版权、商标、专利或其他所有权利，以依法分享和传播上传的文件。
禁止内容: 我们没有义务监控用户上传的内容，严禁上传包含儿童色情、非法、侵权、诽谤性、淫秽或其他违法违规内容的文件。
无担保: 本网站按“现状”提供服务，不保证服务不会中断，也不保证服务的及时性、安全性和错误发生。虽然我们会尽力确保服务质量和安全，但我们不对您使用本服务可能引起的任何形式的数据丢失或损坏承担责任。',
    prompt1: '将文字、文件拖、粘贴到此处，或 ',
    prompt2: '天数<7或限制次数（24h后删除）',
    prompt3: '请输入您要寄出的文本，支持MarkDown格式',
    share: '分享',
    textShare: '文本分享',
    clickUpload: '点击上传',
    pleaseInputExpireValue: '请输入有效期',
    expireStyle: '过期方式',
    expireData: {
      day: '天数',
      hour: '小时',
      forever: '永久',
      minute: '分钟',
      count: '次数'
    },
    expireValue: {
      day: '天',
      hour: '时',
      minute: '分',
      count: '次'
    },
    fileType: {
      file: '文件',
      text: '文本'
    }
  },
  fileBox: {
    copySuccess: '复制成功',
    inputNotEmpty: '请输入五位取件码',
    fileBox: '文件箱',
    textDetail: '文本详情',
    copy: '复 制',
    close: '关 闭',
    delete: '删 除',
    download: '点 击 下 载',
    detail: '查 看 详 情',
    copyLink: '复制链接',
  },
  admin: {
    about: {
      source1: '本项目开源于Github：',
      source2: 'FileCodeBox'
    },
    settings: {
      name: '网站名称',
      description: '网站描述',
      keywords: '关键词',
      background: '背景图片',
      admin_token: '管理密码',
      uploadSize: '文件大小',
      uploadSizeNote: '最大文件大小，单位:（Bytes),1mb=1 * 1024 * 1024',
      openUpload: {
        title: '开启上传',
        open: '开启游客上传',
        close: '关闭游客上传',
        note: '关闭之后需要登录后台方可上传',
      },
      file_storage: {
        title: '存储引擎',
        local: '本地存储',
        s3: 'S3存储',
        note: '更新后需要重启FileCodeBox',
      },
      mei: '每',
      minute: '分钟',
      upload: '上传',
      files: '个文件',
      allow: '允许',
      errors: '次错误',
      save: '保存',
      saveSuccess: '保存成功',
    },
    fileView: {
      code: '取件码',
      prefix: '文件前缀',
      suffix: '文件后缀',
      text: '文本',
      used_count: '已使用次数',
      expired_count: '可用次数',
      size: '文件大小',
      expired_at: '过期时间',
      file_path: '文件路径',
      action: '操作',
      delete: '删除',
    },
    menu: {
      fileManage: '文件管理',
      systemSetting: '系统设置',
      about: '关于我们',
      color: '颜色模式',
      signout: '退出登录',
    },
    login: {
      managePassword: '管理密码',
      passwordNotEmpty: '密码不能为空',
      login: '登 录',
      loginSuccess: '登录成功',
      loginError: '登录失败',
    }
  }
};