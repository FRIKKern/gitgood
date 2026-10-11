import path from 'node:path'

// Each reference directory has one discoverable entry point. Existing files stay
// at stable URLs; adding a document also requires adding its navigation link.
export const documentationIndexes = [
  ['docs', 'docs/README.md'],
  ['docs/implementation', 'docs/implementation/README.md'],
  ['docs/decisions', 'docs/decisions/README.md']
]

export function documentationProblems(files, read) {
  const names = files.map(file => file.replaceAll('\\', '/'))
  const errors = []
  for (const [directory, index] of documentationIndexes) {
    if (!names.includes(index)) {
      errors.push('Missing documentation index: ' + index)
      continue
    }
    const linked = new Set()
    for (const [, url] of read(index).matchAll(/!?\[[^\]]*\]\(([^)]+)\)/g)) {
      if (/^(https?:|mailto:|#)/.test(url)) continue
      const target = decodeURIComponent(url.split('#')[0])
      linked.add(path.posix.normalize(path.posix.join(directory, target)))
    }
    for (const file of names) {
      if (file !== index && file.endsWith('.md') && path.posix.dirname(file) === directory && !linked.has(file)) {
        errors.push('Unindexed document: ' + file + '; add a descriptive link in ' + index)
      }
    }
  }
  return errors
}
