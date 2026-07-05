// Map source URLs to display names. Full URLs are never shown in the UI —
// only the site name — so a malformed/unresolvable URL can never surface.
const SOURCE_NAMES = {
  'ambitionbox.com': 'AmbitionBox',
  'geeksforgeeks.org': 'GeeksforGeeks',
  'interviewbit.com': 'InterviewBit',
  'reddit.com': 'Reddit',
  'teamblind.com': 'Blind',
  'medium.com': 'Medium',
  'glassdoor.com': 'Glassdoor',
  'linkedin.com': 'LinkedIn',
  'indeed.com': 'Indeed',
  'github.io': 'GitHub Pages',
  'quora.com': 'Quora',
  'stackoverflow.com': 'Stack Overflow',
  'levels.fyi': 'Levels.fyi',
  'naukri.com': 'Naukri',
}

export function sourceNames(urls = []) {
  const names = new Set()
  for (const u of urls) {
    let host
    try {
      host = new URL(u).host.replace(/^www\./, '')
    } catch {
      continue // not a valid URL — drop it rather than display it
    }
    const known = Object.keys(SOURCE_NAMES).find((d) => host === d || host.endsWith(`.${d}`))
    names.add(known ? SOURCE_NAMES[known] : host)
  }
  return [...names]
}
