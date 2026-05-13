// Small shared GitHub Actions helpers for the pipeline-trigger routes.
// Kept tight on purpose — auth, headers, and the in-flight check are all
// the route handlers need. Anything heavier (queue tracking, retry
// policy) belongs in its own module.

export const GH_API = 'https://api.github.com'

export function ghHeaders(pat: string) {
  return {
    Authorization: `Bearer ${pat}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'Content-Type': 'application/json',
    'User-Agent': 'job-search-agent-v3',
  }
}

// GitHub's run.status enum has grown over time. We list the *non*-terminal
// values explicitly so a future addition (e.g. another queue-style state)
// doesn't accidentally let us dispatch on top of a still-running batch.
const NON_TERMINAL_STATUSES = new Set([
  'queued',
  'in_progress',
  'requested',
  'waiting',
  'pending',
  'action_required',
])

export type WorkflowRunSummary = {
  id: number
  status: string
  html_url: string
}

/**
 * Look up the latest `workflow_dispatch` run for the given workflow file.
 * Returns the run iff it is currently non-terminal — i.e. we should NOT
 * dispatch a second one.
 *
 * Soft-fails to `null` on any GitHub API hiccup: if we can't tell, let
 * the caller try the dispatch and fail loudly there instead of silently
 * blocking the user. A single API outage shouldn't lock the pipeline
 * button forever.
 */
export async function findInflightDispatch(
  owner: string,
  repo: string,
  workflowFile: string,
  pat: string,
): Promise<WorkflowRunSummary | null> {
  const url =
    `${GH_API}/repos/${owner}/${repo}/actions/workflows/${workflowFile}` +
    `/runs?per_page=1&event=workflow_dispatch`
  let res: Response
  try {
    res = await fetch(url, { headers: ghHeaders(pat), cache: 'no-store' })
  } catch {
    return null
  }
  if (!res.ok) return null
  let data: { workflow_runs?: WorkflowRunSummary[] }
  try {
    data = (await res.json()) as { workflow_runs?: WorkflowRunSummary[] }
  } catch {
    return null
  }
  const latest = data.workflow_runs?.[0]
  if (!latest) return null
  return NON_TERMINAL_STATUSES.has(latest.status) ? latest : null
}
