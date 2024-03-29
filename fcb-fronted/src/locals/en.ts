export default {
  send: {
    mzsm:'Disclaimers',
    alert:'According to the relevant provisions of the Cybersecurity Law of the People\'s Republic of China, the Criminal Law of the People\'s Republic of China, the Law on Public Security Administration Punishments of the People\'s Republic of China, and other relevant regulations, the dissemination or storage of illegal or irregular content may be subject to corresponding penalties, and those who commit serious offenses will bear criminal responsibility. Please refrain from uploading illegal files. This website firmly cooperates with relevant departments to ensure the security and harmony of online content, and to create a green cyber environment.',
    prompt1: 'Drag and drop text or files here, or ',
    prompt2: 'Days <7 or limited times (deleted after 24h)',
    prompt3: 'Please enter the text you want to send',
    share: 'Share',
    textShare: 'Text Share',
    clickUpload: 'Click to upload',
    pleaseInputExpireValue: 'Please enter expiration value',
    expireStyle: 'Expiration style',
    expireData: {
      day: 'Days',
      hour: 'Hours',
      forever: 'Forever',
      minute: 'Minutes',
      count: 'Times'
    },
    expireValue: {
      day: 'Days',
      hour: 'Hours',
      minute: 'Minutes',
      count: 'Times'
    },
    fileType: {
      file: 'File',
      text: 'Text'
    }
  },
  fileBox: {
    copySuccess: 'Copied successfully',
    inputNotEmpty: 'Please enter the five-digit pickup code',
    fileBox: 'File Box',
    textDetail: 'Text Detail',
    copy: 'Copy',
    close: 'Close',
    delete: 'Delete',
    download: 'Click to download',
    detail: 'View details',
    copyLink: 'Copy link',
  },
  admin:{
    about:{
      source1:'This project is open source on Github: ',
      source2:'FileCodeBox'
    },
    settings: {
      name: 'Website Name',
      description: 'Website Description',
      keywords: 'Keywords',
      uploadlimit:'Upload Limit',
      errorlimit:'Error Limit',
      background: 'Background Image',
      admin_token: 'Admin Password',
      uploadSize: 'File Size',
      uploadSizeNote: 'Maximum file size, unit: (bit), 1mb = 1 * 1024 * 1024',
      openUpload: {
        title: 'Enable Upload',
        open: 'Enable Guest Upload',
        close: 'Disable Guest Upload',
        note: 'After disabling, login to the backend is required for uploading.',
      },
      file_storage: {
        title: 'Storage Engine',
        local: 'Local Storage',
        s3: 'S3 Storage',
        note: 'FileCodeBox needs to be restarted after updating.',
      },
      mei: 'Every',
      minute: 'Minutes',
      upload: 'Upload',
      files: 'Files',
      allow: 'Allow',
      errors: 'Errors',
      save: 'Save',
      saveSuccess: 'Saved successfully',
    },
    fileView: {
      code: 'Access Code',
      prefix: 'File Prefix',
      suffix: 'File Suffix',
      text: 'Text',
      used_count: 'Used Count',
      expired_count: 'Available Count',
      size: 'File Size',
      expired_at: 'Expiration Time',
      file_path: 'File Path',
      action: 'Action',
      delete: 'Delete',
      delete_success: 'Delete successful',
      forever: 'Forever',
      unlimited_count: 'Unlimited',
      download: 'Download',
      download_fail: 'File save failed, please try again later~',
    },
    menu: {
      fileManage: 'File Management',
      systemSetting: 'System Settings',
      about: 'About Us',
      color: 'Color Mode',
      signout: 'Sign Out',
    },
    login: {
      managePassword: 'Admin Password',
      passwordNotEmpty: 'Password cannot be empty',
      login: 'Login',
      loginSuccess: 'Login successful',
      loginError: 'Login failed',
    }
  }
}
