import { readFile } from 'node:fs/promises'
import ts from 'typescript'

export async function moduleUrl(path, dependencies = {}) {
  const source = await readFile(new URL('../src/' + path, import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  })
  const code = outputText.replace(
    /from ['"]([^'"]+)['"]/g,
    (statement, name) => dependencies[name] ? 'from ' + JSON.stringify(dependencies[name]) : statement,
  )
  return 'data:text/javascript;base64,' + Buffer.from(code).toString('base64')
}
