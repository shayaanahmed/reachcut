# CircleCI

ReachCut uses CircleCI for continuous integration. The initial pipeline validates
the API and web application on every branch and pull request. After both jobs pass
on `main`, it also verifies that the production API and web Docker images build.

The pipeline deliberately does not publish images or deploy anything. Registry
publishing will be added as a separate release workflow after the private registry,
image-signing identity, and release policy are configured.

## Connect the repository

1. Sign in to CircleCI using the account that can access the private repository.
2. Create a CircleCI project for the ReachCut repository.
3. Select the option to use the existing `.circleci/config.yml` file.
4. Trigger the first pipeline from `main`.

No project secrets or environment variables are required for the initial pipeline.
Do not add application OAuth credentials, customer tokens, model credentials, or
production `.env` contents to CircleCI.

## Pipeline jobs

| Job | Runs | Responsibility |
| --- | --- | --- |
| `api-quality` | Every branch and pull request | Installs the locked Python environment, runs Ruff, mypy, and pytest |
| `web-quality` | Every branch and pull request | Installs the locked pnpm workspace, runs ESLint, Prettier, TypeScript, and Vitest |
| `docker-build` | `main`, after both quality jobs | Builds both production images without publishing them |

The Python and pnpm caches contain dependency downloads only. They are performance
optimizations; locked installs still run on every job.

## Validate locally

Validate the CircleCI syntax before pushing:

```bash
circleci config validate .circleci/config.yml
```

Run the same project checks used by the pipeline:

```bash
pnpm check
pnpm test
```

Production Docker builds can be verified with:

```bash
docker build --file apps/api/Dockerfile --tag reachcut-api:local .
docker build --file apps/web/Dockerfile --tag reachcut-web:local .
```

## Reading failures

Open a failed workflow in CircleCI, select the red job, and then open the first red
step. The first error in that step is normally the useful one; later failures may be
consequences of it.

- A dependency-install failure usually points to a lockfile or registry problem.
- A quality failure should be reproduced with `pnpm check`.
- A test failure should be reproduced with `pnpm test`.
- A Docker failure should be reproduced with the relevant `docker build` command.

Fix the underlying problem locally, commit the change, and push it. CircleCI starts a
new workflow automatically.

## Branch protection

After the first successful pipeline, configure the Git provider to require
`api-quality` and `web-quality` before merging into `main`. Keep `docker-build` as a
post-merge release-readiness check initially because it is slower and consumes a
remote Docker environment.

## Future release workflow

The next CI milestone will be a separate workflow triggered by version tags. It will:

1. Re-run checks and tests.
2. Build immutable API and web images.
3. Scan and sign the images.
4. Push them to the private registry.
5. Record their digests.
6. Generate the customer release manifest and release notes.

Registry and signing credentials must be stored in a restricted CircleCI context,
not directly in the YAML file. Only the release job should receive that context.
