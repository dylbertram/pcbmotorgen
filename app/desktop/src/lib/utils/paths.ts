/** Display the final path component without changing the path itself. */
export function baseName(path: string): string {
  return path.slice(Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\")) + 1);
}

/** Parent directory including its final separator, or null for a bare name. */
export function parentDirectory(path: string): string | null {
  const index = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return index < 0 ? null : path.slice(0, index + 1);
}
