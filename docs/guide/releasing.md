# 版本发布

项目采用 Semantic Versioning 和 Conventional Commits 管理版本。

首次启用时，需要在后端 GitHub 仓库完成以下设置：

- `Settings → Actions → General → Workflow permissions` 选择读写权限，并允许
  GitHub Actions 创建 Pull Request。前端仓库只需要默认的 Actions 读取权限。
- 保持 Squash merge 可用；自动发布工作流会等待必需检查通过后合并发布 PR。
- 后端仓库配置 `DOCKER_USERNAME` 和 `DOCKER_PASSWORD` Actions Secrets。

1. 日常提交使用 `feat:`、`fix:` 等 Conventional Commits 前缀并合入主分支。
2. Release Please 自动创建并合并发布 PR，更新 `VERSION` 和更新日志。
3. 工作流随后自动创建 `vX.Y.Z`、GitHub Release 并触发正式镜像构建。
4. 正式镜像发布 `X.Y.Z`、`X.Y` 和 `latest`；分支镜像使用 `dev` 或 `edge-*`。
5. 镜像构建时自动读取两个前端仓库默认分支的最新提交，无需手工同步版本。

因此每次合入主分支的 `fix:`、`feat:` 或破坏性变更都会自动产生对应的
Patch、Minor 或 Major 版本。`docs:`、`chore:` 等不影响版本的提交不会单独发版。

后端运行版本来自 `VERSION`。容器分支构建通过 `APP_VERSION` 注入带提交号的
开发版本；正式标签必须与 `VERSION` 完全一致。Docker 镜像的 OCI 标签还记录
后端和两个前端仓库当次解析到的精确提交，便于定位构建内容。
