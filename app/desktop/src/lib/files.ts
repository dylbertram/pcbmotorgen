/**
 * Native file-system helpers for export features.
 *
 * Currently one primitive: "save string content via native dialog".
 * Every export target shares this save flow.
 */

import { save } from "@tauri-apps/plugin-dialog";
import { writeTextFile } from "@tauri-apps/plugin-fs";

/**
 * Show the native save dialog and write `content` to the chosen file.
 *
 * @param content text to write
 * @param fileName suggested file name shown in the dialog
 * @param extensions file extensions to offer (no leading dot)
 * @returns the chosen absolute path, or `null` if the user cancelled
 */
export async function saveTextToFile(
  content: string,
  fileName: string,
  extensions: string[],
): Promise<string | null> {
  const filePath = await save({
    defaultPath: fileName,
    filters: [{ name: `${extensions.join("/").toUpperCase()} files`, extensions }],
  });
  // User cancelled the dialog.
  if (filePath === null) return null;
  await writeTextFile(filePath, content);
  return filePath;
}