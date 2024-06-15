export default {
  send: {
    disclaimers: '免責聲明',
    alert: '根據《中華人民共和國網絡安全法》、《中華人民共和國刑法》、《中華人民共和國治安管理處罰法》等相關規定。 傳播或存儲違法、違規內容，會受到相關處罰，嚴重者將承擔刑事責任。請勿上傳非法文件，本站堅決配合相關部門，確保網絡內容的安全，和諧，打造綠色網絡環境。',
    prompt1: '將文字、文件拖、粘貼到此處，或 ',
    prompt2: '天數<7或限制次數（24h後刪除）',
    prompt3: '請輸入您要寄出的文本，支持MarkDown格式',
    share: '分享',
    textShare: '文本分享',
    clickUpload: '點擊上傳',
    pleaseInputExpireValue: '請輸入有效期',
    expireStyle: '過期方式',
    expireData: {
      day: '天數',
      hour: '小時',
      forever: '永久',
      minute: '分鐘',
      count: '次數'
    },
    expireValue: {
      day: '天',
      hour: '時',
      minute: '分',
      count: '次'
    },
    fileType: {
      file: '文件',
      text: '文本'
    }
  },
  fileBox: {
    copySuccess: '複製成功',
    inputNotEmpty: '請輸入五位取件碼',
    sendFileBox: '寄件箱',
    receiveFileBox: '收件箱',
    textDetail: '文本詳情',
    copy: '複 制',
    close: '關 閉',
    delete: '刪 除',
    download: '點 擊 下 載',
    detail: '查 看 詳 情',
    copyLink: '複製連結',
  },
  admin: {
    about: {
      source1: '本專案開源於Github：',
      source2: 'FileCodeBox'
    },
    settings: {
      name: '網站名稱',
      description: '網站描述',
      uploadlimit: '上傳限制',
      explain:'介面說明',
      errorlimit: '錯誤限制',
      keywords: '關鍵詞',
      background: '背景圖片',
      admin_token: '管理密碼',
      uploadSize: '文件大小',
      uploadSizeNote: '最大文件大小，單位:（Bytes),1mb=1 * 1024 * 1024',
      openUpload: {
        title: '開啟上傳',
        open: '開啟遊客上傳',
        close: '關閉遊客上傳',
        note: '關閉之後需要登入後台方可上傳',
      },
      file_storage: {
        title: '存儲引擎',
        local: '本地存儲',
        s3: 'S3存儲',
        note: '更新後需要重新啟動FileCodeBox',
      },
      mei: '每',
      minute: '分鐘',
      upload: '上傳',
      files: '個文件',
      allow: '允許',
      errors: '次錯誤',
      save: '保存',
      saveSuccess: '保存成功',
    },
    fileView: {
      code: '取件碼',
      prefix: '文件前綴',
      suffix: '文件後綴',
      text: '文本',
      used_count: '已使用次數',
      expired_count: '可用次數',
      size: '文件大小',
      expired_at: '過期時間',
      file_path: '文件路徑',
      action: '操作',
      delete: '刪除',
      delete_success: '刪除成功',
      forever: '永久有效',
      unlimited_count: '不限次數',
      download: '下載',
      download_fail: '文件保存失敗，請稍後再試~',
    },
    menu: {
      fileManage: '文件管理',
      systemSetting: '系統設置',
      about: '關於我們',
      color: '顏色模式',
      signout: '退出登錄',
    },
    login: {
      managePassword: '管理密碼',
      passwordNotEmpty: '密碼不能為空',
      login: '登 錄',
      loginSuccess: '登錄成功',
      loginError: '登錄失敗',
    }
  }
};