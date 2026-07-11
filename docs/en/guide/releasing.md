# Releasing

The project uses Semantic Versioning and Conventional Commits.

Complete these settings once in both GitHub repositories:

- In `Settings → Actions → General → Workflow permissions`, grant read/write
  access and allow GitHub Actions to create pull requests.
- Keep squash merging enabled. The release workflow waits for required checks
  before merging the release pull request.
- Add `DOCKER_USERNAME` and `DOCKER_PASSWORD` Actions secrets to the backend repository.

1. Merge commits using Conventional Commit types such as `feat:` and `fix:` into the default branch.
2. Release Please creates and merges the release pull request and updates `VERSION` and the changelog.
3. The workflow then creates `vX.Y.Z`, a GitHub Release, and dispatches the production image build.
4. Releases publish `X.Y.Z`, `X.Y`, and `latest`; branches publish `dev` or `edge-*` images.
5. Each image build resolves the latest commit from both frontend default branches automatically.

Every `fix:`, `feat:`, or breaking change merged into the default branch therefore
creates a Patch, Minor, or Major release automatically. Non-release commits such
as `docs:` and `chore:` do not publish a release on their own.

The backend runtime version comes from `VERSION`. Container branch builds inject a
commit-qualified development version through `APP_VERSION`; release tags must exactly
match `VERSION`. OCI image labels record the resolved backend and frontend commits for traceability.
