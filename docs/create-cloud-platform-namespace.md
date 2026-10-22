# Create Cloud Platform Namespace

The COAT Cost API is hosted on the MOJ Cloud Platform, a shared Kubernetes cluster. Each environment has its own namespace. Namespaces are defined as code in [`cloud-platform-environments`](https://github.com/ministryofjustice/cloud-platform-environments), and a pipeline applies them to the cluster once a PR is merged. Nothing is created directly with `kubectl`.

This doc covers what exists, how to access it, and how the namespaces were created, including the issues hit along the way.

> **The [Cloud Platform user guide](https://user-guide.cloud-platform.service.justice.gov.uk/) is the source of truth.** The steps here follow its [Creating a Cloud Platform environment](https://user-guide.cloud-platform.service.justice.gov.uk/documentation/getting-started/env-create.html) guide, with notes on what we ran into. If anything here disagrees with the user guide, follow the user guide.

## Namespaces

| Namespace | Environment | Production | Created in |
|---|---|---|---|
| `coat-cost-api-dev` | development | false | [#47367](https://github.com/ministryofjustice/cloud-platform-environments/pull/47367) |
| `coat-cost-api-prod` | production | true | [#47368](https://github.com/ministryofjustice/cloud-platform-environments/pull/47368) |

## Access

Admin access to both namespaces is granted to the `cloud-optimisation-and-accountability` GitHub team through a RoleBinding (`01-rbac.yaml`). The access applies to these namespaces only.

To connect:

1. Download a kubeconfig from the [Cloud Platform login page](https://login.cloud-platform.service.justice.gov.uk/) (sign in with GitHub). See [Connecting to the Cloud Platform's Kubernetes cluster](https://user-guide.cloud-platform.service.justice.gov.uk/documentation/getting-started/kubectl-config.html)

2. Save it as `~/.kube/config`, restrict it with `chmod 600 ~/.kube/config`, then run `kubectl config use-context live.cloud-platform.service.justice.gov.uk`.

To check your access:

```bash
kubectl get namespace coat-cost-api-dev coat-cost-api-prod

kubectl get rolebinding -n coat-cost-api-dev

kubectl auth can-i create deployments -n coat-cost-api-dev   # << this should return yes
```

If you get `Forbidden`, check that your token includes the team:

```bash
cloud-platform kubecfg id-token-claims
```

Look for `github:cloud-optimisation-and-accountability` in the groups list. The token is a snapshot from when the kubeconfig was downloaded, so if you were added to the team since then, download a fresh one.

## Observations/notes

> **Caveat:** observed when deploying in October 2026. Cloud Platform may have changed since, so check the user guide if something doesn't match.

These are the parts that aren't obvious from the files themselves.

- **Business unit is `Platforms`, not `OCTO`.** The MoJ tagging standard uses `OCTO`, but Cloud Platform's policy (`policy/namespace.rego`) only accepts a fixed list that doesn't include it, and the PR check fails if it's used. Cloud Platform aren't changing the list ahead of the move to CP3.
- **Pod security is `restricted`.** Pods are rejected unless they run as a non-root user, disallow privilege escalation and drop Linux capabilities. The API's Docker image needs to meet this before it can be deployed.
- **Network policies only restrict incoming traffic.** Pods accept traffic from the ingress controller and from other pods in the same namespace. Outgoing traffic isn't restricted, so calls out to AWS (for example Athena) aren't blocked at the network level. They still need IAM permissions.


## Step-by-step: Creating a namespace

This is how the namespaces above were created. It's useful if one needs recreating, or for setting up a new COAT service.

### 1. Install the tools

```bash
brew trust ministryofjustice/cloud-platform-tap

brew install ministryofjustice/cloud-platform-tap/cloud-platform-cli

cloud-platform version
```

You also need `kubectl` within one minor version of the cluster. Check what you have, and what the cluster runs, rather than relying on the docs:

```bash
kubectl version   
```

At the time of writing (October 2026), the cluster was on 1.35, while parts of the Cloud Platform guide still said 1.32 or 1.34.

### 2. Clone the environments repo and branch from main

```bash
git clone https://github.com/ministryofjustice/cloud-platform-environments.git

cd cloud-platform-environments

git checkout -b <namespace
```

**Observation:** Create namespaces one at a time. Take one namespace all the way to merged before starting the next, then branch the next one from the updated `main`. This keeps each PR small and easy to review, and avoids the `.checksum` conflict described in step 5.

### 3. Run the CLI

```bash
cloud-platform environment create
```

The values used for the COAT Cost API, which follow the existing COAT namespaces:

| Prompt | Value |
|---|---|
| Name | `coat-cost-api-dev` / `coat-cost-api-prod` |
| Environment | `development` / `production` |
| Sandbox? | `no` |
| Application | `COAT Cost API` |
| GitHub Team | `cloud-optimisation-and-accountability` |
| Business Unit | `Platforms` |
| Team Slack Channel | `cloud-optimisation-and-accountability-team` |
| Service Area | `Hosting` |
| Team Email | `cloudoptimisationandaccountabilityteam@justice.gov.uk` |
| Github Repo | `https://github.com/ministryofjustice/coat-cost-api` |
| Team | `COAT` |

The last prompt ("Team") only feeds the `owner` annotation. Use `COAT` to match the other COAT namespaces.

### 4. Review the generated files

The CLI creates five YAML files and three Terraform files, and updates `.checksum` at the repo root. Compare them with an existing COAT namespace (for example `coat-chatbot-frontend-dev`).

For prod, set `is-production` to `"true"` in both `00-namespace.yaml` and `resources/variables.tf`. The CLI leaves it as `"false"` (see [Issues and fixes](#issues-and-fixes)).

Would be great if you could run the following policy test locally. To check a file against Cloud Platform's policy before pushing:

```bash
brew install conftest

conftest test namespaces/live.cloud-platform.service.justice.gov.uk/<namespace>/00-namespace.yaml --policy policy
```

Note: If anything conflicts with the policy, conftest will flag it before the PR check does.

### 5. Commit and raise a PR

```bash
git add namespaces/live.cloud-platform.service.justice.gov.uk/<namespace>
git commit -m "Create <namespace> namespace"
git push -u origin <namespace>
```

Raise one PR per environment, as PRs that contain more than one namespace are rejected.

**About `.checksum`:** the CLI also updates `.checksum` at the repo root. Neither the Cloud Platform guide nor anything else in the repo uses it (as of October 2026), and many recent namespace PRs leave it out. We included it, which caused a merge conflict between our dev and prod PRs. Leaving it out avoids that. If you're unsure, ask in #ask-cloud-platform. To discard the change before committing:



### 6. Get it reviewed

post the PR links in [#ask-cloud-platform](https://mojdt.slack.com/archives/C57UPMZLY). Once approved, the PR author merges.

### 7. Merge and verify

Merge one PR at a time. The Apply pipeline creates the namespace within a few minutes. You will be given a concourse link at the bottom of your approved PR by which you can check the build in CP. Locally you can run the access checks from the [Access](#access) section.

## Issues and fixes

| Issue | Cause | Fix |
|---|---|---|
| `kubectl` version outside the supported range | Docker Desktop installs its own `kubectl` at `/usr/local/bin` and updates it on its own schedule | Install a pinned version in `~/.local/bin`, which comes first on `PATH`. Don't replace Docker's copy. |
| Existing `~/.kube/config` at risk of being overwritten | Docker Desktop can create one for its local Kubernetes | Check `ls ~/.kube` first. If one exists, merge the configs rather than replacing it. |
| `owner` annotation doesn't match other COAT namespaces | The final "Team" prompt feeds `owner` | Answer `COAT`. If it's already generated, delete the folder, `git restore .checksum`, and re-run the CLI. |
| Prod namespace has `is-production: "false"` | The CLI doesn't ask, and doesn't set it from the environment | Check/edit both `00-namespace.yaml` and `resources/variables.tf` to `"true"` |
| PR check fails with `Invalid business-unit annotation` | Cloud Platform's policy only allows a fixed list of business units | Use a value from the list in `policy/namespace.rego` (`Platforms` for COAT - as of October 2026) |
| Merge conflict on `.checksum` | `.checksum` only holds the most recently created namespace, so namespace PRs that include it conflict with each other. We hit this by raising dev and prod together. | Leave `.checksum` out of the PR. If it's already included and conflicts, merge `main` into the branch and keep the branch's own version (steps below). |
| PR shows "Review required" after fixing a conflict | New commits can dismiss existing approvals | Ask for a re-approval in the #ask-cloud-platform thread. |

Fixing a `.checksum` conflict:

```bash
git checkout <your-branch>

git fetch origin

git merge origin/main

git checkout --ours .checksum   # keep this branch's entry

git add .checksum

git commit --no-edit

git push
```

`git status` will list lots of other teams' files from `main` during the merge. That's expected, and they won't appear in the PR diff.

## Next steps

The namespaces are only the base. Follow-on work:

- **App deployment infrastructure:** an ECR repository for the image, a service account for GitHub Actions deploys, and cross-account access to Athena in the COAT AWS account through IRSA. The pods run in Cloud Platform's AWS account, not COAT's, so local AWS credentials won't carry over.
- **DNS:** a hostname and ingress for the API.