export default {
  send: {
    mzsm:'Disclaimers',
    alert:'Thank you for choosing our file-sharing service. Before you use this website, please carefully read the following disclaimer:

Data Encryption: This website does not employ end-to-end encryption technology. This means that during the upload or download of files, data may be accessed by unauthorized third parties during transmission. Therefore, we strongly recommend that you do not upload or share any sensitive, confidential, or personal privacy data through our service.

Content Responsibility: Users are wholly responsible for all content they upload to the website. Users must ensure they own or have obtained appropriate copyright, trademark, patent, or other property rights to legally share and disseminate the uploaded files.

Prohibited Content: We have no obligation to monitor the content uploaded by users and strictly forbid the uploading of files containing child pornography, illegal activities, infringement, defamation, obscenity, or any other unlawful or regulatory-violating content.

No Warranty: The services of this website are provided “as is” with no guarantee of service continuity, nor of the timeliness, security, and error occurrence of the service. While we strive to ensure the quality and safety of the service, we do not take responsibility for any form of data loss or damage that could occur as a result of your use of this service.',
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
