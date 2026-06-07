# 下一步开发计划

本文档记录 FileCodeBox 下一阶段开发优先级、并行拆分方式、验收标准和质量门禁。

## 背景

当前工作区包含两个独立仓库：

- `FileCodeBox`：FastAPI 后端，包含接口、存储、管理后台 API、文档和后端测试。
- `FileCodeBoxFronted`：Vue 3 + Vite 前端，包含公开取件/发件页和管理后台界面。

近期提交主要集中在 S3 存储、取件码归一化、文件类型限制、主题资源加载、前端管理页和上传下载体验。

下一阶段应优先处理用户可见断点和自动化回归保护，再推进大模块拆分。

## 优先级总览

### P0：补齐取件文件预览链路

目标：打通前端已存在但尚未完整接线的文件预览能力。

涉及模块：

- `RetrievewFileView.vue`
- `FileDetailModal.vue`
- `MediaPreviewModal.vue`
- `useRetrieveFlow.ts`

主要工作：

1. 在取件详情弹窗中绑定文件预览事件。
2. 在取件页渲染媒体预览弹窗。
3. 确认图片、视频、音频、PDF 等可预览文件能正常打开。
4. 保持关闭、下载、错误提示等状态行为一致。

验收标准：

```bash
pnpm check:architecture
pnpm build
```

手工验收：

1. 上传非文本文件并获取取件码。
2. 取件后打开详情弹窗。
3. 点击预览，确认弹窗可打开。
4. 确认关闭和下载动作正常。

### P0：建立最小前端测试体系

目标：为核心前端流程建立可持续的自动化回归保护。

现状：

- 前端暂无测试目录。
- `package.json` 中暂无 `test` 脚本。
- 最近改动涉及上传、下载、Markdown 预览、配置表单等高风险路径。

建议引入：

```bash
vitest
@vue/test-utils
jsdom
```

首批测试范围：

- 文件类型限制规则。
- 过期时间限制校验。
- Markdown 渲染和 HTML 清洗。
- 下载动作解析。
- 预签名上传与分片上传提交分支。

验收标准：

```bash
pnpm test
```

要求：

- 测试能在 60 秒内完成。
- 核心工具函数至少具备首批单元测试。
- 测试脚本不修改源码文件。

### P1：后端上传与存储回归加固

目标：把近期修复沉淀为后端测试，降低存储和上传链路回归风险。

涉及模块：

- `apps/base/views.py`
- `core/storage.py`
- `main.py`
- `tests/`

优先测试场景：

1. 预签名上传 `init` / `confirm` / `cancel`。
2. 代理上传文件大小校验。
3. `allowed_file_types` 的扩展名、MIME、通配规则。
4. S3 `file_exists` 的 `head_object` 失败降级逻辑。
5. 主题资源路径穿越保护。

验收标准：

```bash
pytest
```

要求：

- 测试使用临时目录和替身对象，避免污染 `data/`。
- 外部存储相关测试不依赖真实网络或真实 S3。
- 异常路径和边界值必须覆盖。

### P1：调整质量脚本

目标：区分“检查”和“自动修复”，避免 CI 或验证命令改写源码。

当前问题：

```json
"lint": "eslint . --fix"
```

建议调整：

```json
{
  "lint": "eslint . --fix",
  "lint:check": "eslint ."
}
```

推荐前端验证顺序：

```bash
pnpm check:architecture
pnpm type-check
pnpm lint:check
pnpm test
pnpm build
```

### P2：拆分管理文件模块

目标：降低管理文件页面和业务 composable 的维护复杂度。

现状：

- `FileManageView.vue` 体量较大。
- `useAdminFiles.ts` 同时承载列表、筛选、视图预设、批量操作、详情、元数据、下载和预览等职责。

拆分顺序：

1. 抽纯函数：筛选参数归一化、视图预设归一化、摘要计算、详情视图模型转换。
2. 抽 composable：批量操作、详情弹窗、元数据编辑、视图预设。
3. 抽 UI 子组件：批量工具栏、筛选栏、详情侧栏、预设选择器。

约束：

- 每次只拆一块。
- 拆分前后行为保持一致。
- 先给纯函数补测试，再推进 UI 拆分。

## 并行开发安排

第一轮可并行拆分为四个互不冲突的任务：

1. 前端 A：接线取件文件预览。
2. 前端 B：搭建 Vitest 与首批工具函数测试。
3. 后端 C：补充上传和存储回归测试。
4. 工程 D：新增 `lint:check` 并整理验证命令。

合并前统一验证：

```bash
cd FileCodeBoxFronted
pnpm check:architecture
pnpm type-check
pnpm lint:check
pnpm test
pnpm build

cd ../FileCodeBox
pytest
```

## 质量门禁

每个开发任务完成时必须记录：

- 改动范围。
- 关键设计决策。
- 执行过的验证命令。
- 未覆盖风险和后续事项。

涉及上传、删除、存储、认证、配置等功能时，必须补充异常路径测试。

## 推荐执行顺序

1. 先完成 P0 的取件预览接线。
2. 同步建立前端最小测试体系。
3. 补齐后端上传和存储回归测试。
4. 调整前端质量脚本。
5. 等测试保护到位后，再拆分管理文件模块。

结论：下一阶段以“取件预览接线 + 测试体系建设”为主线，先修用户可见断点，再提升长期维护质量。
