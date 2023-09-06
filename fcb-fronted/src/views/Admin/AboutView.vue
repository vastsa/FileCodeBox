<template>
  <main style="text-align: center">
      <span>{{ t('admin.about.source1') }}
        <em>
        <a style="color: #333" href="https://github.com/vastsa/FileCodeBox">{{ t('admin.about.source2') }}</a>
        </em>
      </span>
  </main>
</template>
<script lang="ts" setup>

import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>