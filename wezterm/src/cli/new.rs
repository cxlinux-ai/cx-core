/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
*/
// CX Terminal: Create new projects from templates.
//
// This module provides the `new` command for creating new projects
// from predefined templates. Templates include common project types
// like Rust, Python, Node.js, and more.

use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::Command;

use anyhow::{bail, Context, Result};
use clap::Parser;

/// Command to create a new project from a template.
///
/// # Examples
///
/// ```bash
/// cx-terminal new rust my-project
/// cx-terminal new python --name my-project --dir /path/to/projects
/// cx-terminal new --list
/// ```
#[derive(Debug, Parser, Clone)]
pub struct NewCommand {
    /// The template to use (e.g., "rust", "python", "node")
    #[arg(default_value = "default")]
    pub template: String,

    /// The name of the new project
    #[arg(value_name = "NAME")]
    pub project_name: Option<String>,

    /// The name of the new project
    #[arg(short, long)]
    pub name: Option<String>,

    /// The directory to create the project in
    #[arg(short, long)]
    pub dir: Option<String>,

    /// List available templates
    #[arg(long)]
    pub list: bool,
}

impl NewCommand {
    /// Execute the new command to create a project from template.
    ///
    /// # Returns
    ///
    /// Returns `Ok(())` on success, or an error if project creation fails.
    pub fn run(&self) -> Result<()> {
        if self.list || (self.template == "default" && self.effective_name()?.is_none()) {
            print_available_templates();
            return Ok(());
        }

        let requested_template = self.template.to_lowercase();
        let known_template = find_template(&requested_template);
        let (template, project_name) = match (known_template, self.effective_name()?) {
            (Some(template), Some(project_name)) => (template, project_name),
            (Some(_), None) => {
                bail!(
                    "Project name is required. Try: cx new {} my-project",
                    self.template
                )
            }
            (None, None) if self.project_name.is_none() && self.name.is_none() => {
                let inferred_template = infer_default_template();
                let template = find_template(inferred_template)
                    .context("internal error: inferred template is not registered")?;
                (template, self.template.clone())
            }
            (None, Some(project_name)) if requested_template == "default" => {
                let inferred_template = infer_default_template();
                let template = find_template(inferred_template)
                    .context("internal error: inferred template is not registered")?;
                (template, project_name)
            }
            (None, _) => {
                bail!(
                    "Unknown template '{}'. Run 'cx new --list' to see available templates.",
                    self.template
                )
            }
        };

        validate_project_name(&project_name)?;
        let context = TemplateContext::new(&project_name);
        let base_dir = match &self.dir {
            Some(dir) => PathBuf::from(dir),
            None => std::env::current_dir().context("failed to read current directory")?,
        };
        let target_dir = base_dir.join(&project_name);

        ensure_target_directory_is_ready(&target_dir)?;
        write_template(&target_dir, &template, &context)?;

        if template.create_python_venv {
            create_python_venv(&target_dir)?;
        }

        println!(
            "Created '{}' project '{}' at {}",
            template.name,
            project_name,
            target_dir.display()
        );
        println!("Next steps:");
        for step in template.next_steps.iter() {
            println!("  {}", render(step, &context));
        }

        Ok(())
    }

    fn effective_name(&self) -> Result<Option<String>> {
        match (&self.project_name, &self.name) {
            (Some(_), Some(_)) => {
                bail!("Project name was provided twice. Use either positional NAME or --name.")
            }
            (Some(name), None) | (None, Some(name)) => Ok(Some(name.clone())),
            (None, None) => Ok(None),
        }
    }
}

#[derive(Debug, Clone)]
struct Template {
    name: &'static str,
    description: &'static str,
    files: Vec<TemplateFile>,
    next_steps: Vec<&'static str>,
    create_python_venv: bool,
}

#[derive(Debug, Clone)]
struct TemplateFile {
    path: &'static str,
    contents: &'static str,
}

#[derive(Debug, Clone)]
struct TemplateContext {
    project_name: String,
    package_name: String,
    rust_crate: String,
    python_module: String,
    go_module: String,
}

impl TemplateContext {
    fn new(project_name: &str) -> Self {
        let package_name = sanitize_package_name(project_name);
        let identifier = sanitize_identifier(project_name);

        Self {
            project_name: project_name.to_string(),
            package_name,
            rust_crate: identifier.clone(),
            python_module: identifier.clone(),
            go_module: format!("example.com/{}", identifier),
        }
    }
}

fn print_available_templates() {
    println!("Available templates:");
    for template in templates() {
        println!("  {:<8} {}", template.name, template.description);
    }
    println!();
    println!("Usage:");
    println!("  cx new <template> <name>");
    println!("  cx new --list");
}

fn find_template(name: &str) -> Option<Template> {
    templates()
        .into_iter()
        .find(|template| template.name == name)
}

fn infer_default_template() -> &'static str {
    let current_dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    if current_dir.join("Cargo.toml").exists() {
        "rust"
    } else if current_dir.join("pyproject.toml").exists() {
        "python"
    } else if current_dir.join("go.mod").exists() {
        "go"
    } else if current_dir.join("Dockerfile").exists() {
        "docker"
    } else if current_dir.join("package.json").exists() {
        "node"
    } else {
        "node"
    }
}

fn validate_project_name(name: &str) -> Result<()> {
    if name.trim().is_empty() {
        bail!("Project name cannot be empty.");
    }

    let path = Path::new(name);
    if path.is_absolute() || path.components().count() != 1 {
        bail!("Project name must be a single directory name, not a path.");
    }

    if path.components().any(|component| {
        matches!(
            component,
            Component::ParentDir | Component::CurDir | Component::RootDir | Component::Prefix(_)
        )
    }) {
        bail!("Project name cannot contain path navigation components.");
    }

    if !name
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '.'))
    {
        bail!("Project name may only contain letters, numbers, '.', '-', and '_'.");
    }

    Ok(())
}

fn ensure_target_directory_is_ready(target_dir: &Path) -> Result<()> {
    if target_dir.exists() {
        if !target_dir.is_dir() {
            bail!(
                "Target path already exists and is not a directory: {}",
                target_dir.display()
            );
        }

        if fs::read_dir(target_dir)
            .with_context(|| format!("failed to inspect {}", target_dir.display()))?
            .next()
            .is_some()
        {
            bail!(
                "Target directory already exists and is not empty: {}",
                target_dir.display()
            );
        }
    } else {
        fs::create_dir_all(target_dir)
            .with_context(|| format!("failed to create {}", target_dir.display()))?;
    }

    Ok(())
}

fn write_template(target_dir: &Path, template: &Template, context: &TemplateContext) -> Result<()> {
    for file in template.files.iter() {
        let relative_path = render(file.path, context);
        let output_path = target_dir.join(&relative_path);
        if let Some(parent) = output_path.parent() {
            fs::create_dir_all(parent)
                .with_context(|| format!("failed to create {}", parent.display()))?;
        }

        fs::write(&output_path, render(file.contents, context))
            .with_context(|| format!("failed to write {}", output_path.display()))?;
    }

    Ok(())
}

fn create_python_venv(target_dir: &Path) -> Result<()> {
    let venv_dir = target_dir.join(".venv");
    let status = Command::new("python3")
        .args(["-m", "venv", ".venv"])
        .current_dir(target_dir)
        .status();

    match status {
        Ok(status) if status.success() => Ok(()),
        _ => {
            fs::create_dir_all(&venv_dir)
                .with_context(|| format!("failed to create {}", venv_dir.display()))?;
            fs::write(
                venv_dir.join("README.md"),
                "Create the virtual environment with:\n\n```bash\npython3 -m venv .venv\n```\n",
            )
            .with_context(|| format!("failed to write {}", venv_dir.display()))?;
            Ok(())
        }
    }
}

fn render(input: &str, context: &TemplateContext) -> String {
    input
        .replace("{{project_name}}", &context.project_name)
        .replace("{{package_name}}", &context.package_name)
        .replace("{{rust_crate}}", &context.rust_crate)
        .replace("{{python_module}}", &context.python_module)
        .replace("{{go_module}}", &context.go_module)
}

fn sanitize_package_name(name: &str) -> String {
    let sanitized = name
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch == '-' {
                ch.to_ascii_lowercase()
            } else {
                '-'
            }
        })
        .collect::<String>()
        .trim_matches('-')
        .to_string();

    if sanitized.is_empty() {
        "cx-project".to_string()
    } else {
        sanitized
    }
}

fn sanitize_identifier(name: &str) -> String {
    let mut sanitized = name
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() {
                ch.to_ascii_lowercase()
            } else {
                '_'
            }
        })
        .collect::<String>()
        .trim_matches('_')
        .to_string();

    if sanitized.is_empty() {
        sanitized.push_str("cx_project");
    }

    if sanitized
        .chars()
        .next()
        .is_some_and(|ch| ch.is_ascii_digit())
    {
        sanitized.insert(0, '_');
    }

    sanitized
}

fn templates() -> Vec<Template> {
    vec![
        Template {
            name: "python",
            description: "Python package with pyproject.toml, src layout, and .venv",
            create_python_venv: true,
            next_steps: vec![
                "cd {{project_name}}",
                "source .venv/bin/activate",
                "python -m {{python_module}}",
            ],
            files: vec![
                TemplateFile {
                    path: "pyproject.toml",
                    contents: r#"[project]
name = "{{package_name}}"
version = "0.1.0"
description = "A Python project generated by CX Terminal"
requires-python = ">=3.10"
dependencies = []

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
"#,
                },
                TemplateFile {
                    path: "README.md",
                    contents: r#"# {{project_name}}

Generated with `cx new python`.

## Run

```bash
source .venv/bin/activate
python -m {{python_module}}
```
"#,
                },
                TemplateFile {
                    path: "src/{{python_module}}/__init__.py",
                    contents: r#""""{{project_name}} package."""
"#,
                },
                TemplateFile {
                    path: "src/{{python_module}}/__main__.py",
                    contents: r#"def main() -> None:
    print("Hello from {{project_name}}!")


if __name__ == "__main__":
    main()
"#,
                },
                TemplateFile {
                    path: ".gitignore",
                    contents: r#".venv/
__pycache__/
*.pyc
.pytest_cache/
"#,
                },
            ],
        },
        Template {
            name: "rust",
            description: "Rust binary crate with Cargo.toml and src/main.rs",
            create_python_venv: false,
            next_steps: vec!["cd {{project_name}}", "cargo run"],
            files: vec![
                TemplateFile {
                    path: "Cargo.toml",
                    contents: r#"[package]
name = "{{package_name}}"
version = "0.1.0"
edition = "2021"

[dependencies]
"#,
                },
                TemplateFile {
                    path: "src/main.rs",
                    contents: r#"fn main() {
    println!("Hello from {{project_name}}!");
}
"#,
                },
                TemplateFile {
                    path: ".gitignore",
                    contents: r#"target/
"#,
                },
            ],
        },
        Template {
            name: "node",
            description: "Node.js project with package.json and index.js",
            create_python_venv: false,
            next_steps: vec!["cd {{project_name}}", "npm install", "npm start"],
            files: vec![
                TemplateFile {
                    path: "package.json",
                    contents: r#"{
  "name": "{{package_name}}",
  "version": "0.1.0",
  "type": "module",
  "private": true,
  "scripts": {
    "start": "node index.js",
    "test": "node --test"
  }
}
"#,
                },
                TemplateFile {
                    path: "index.js",
                    contents: r#"console.log("Hello from {{project_name}}!");
"#,
                },
                TemplateFile {
                    path: ".gitignore",
                    contents: r#"node_modules/
.env
"#,
                },
            ],
        },
        Template {
            name: "react",
            description: "React + Vite TypeScript app",
            create_python_venv: false,
            next_steps: vec!["cd {{project_name}}", "npm install", "npm run dev"],
            files: vec![
                TemplateFile {
                    path: "package.json",
                    contents: r#"{
  "name": "{{package_name}}",
  "version": "0.1.0",
  "type": "module",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^19.2.1",
    "react-dom": "^19.2.1"
  },
  "devDependencies": {
    "@types/react": "^19.2.7",
    "@types/react-dom": "^19.2.3",
    "@vitejs/plugin-react": "^5.1.1",
    "typescript": "^5.9.3",
    "vite": "^7.2.6"
  }
}
"#,
                },
                TemplateFile {
                    path: "index.html",
                    contents: r#"<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{{project_name}}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
"#,
                },
                TemplateFile {
                    path: "src/main.tsx",
                    contents: r#"import { createRoot } from "react-dom/client";
import App from "./App";
import "./style.css";

createRoot(document.getElementById("root")!).render(<App />);
"#,
                },
                TemplateFile {
                    path: "src/App.tsx",
                    contents: r#"export default function App() {
  return (
    <main>
      <h1>{{project_name}}</h1>
      <p>React project generated by CX Terminal.</p>
    </main>
  );
}
"#,
                },
                TemplateFile {
                    path: "src/style.css",
                    contents: r#":root {
  color: #18212f;
  background: #f6f8fb;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
}

body {
  margin: 0;
}

main {
  display: grid;
  min-height: 100vh;
  place-content: center;
  text-align: center;
}
"#,
                },
                TemplateFile {
                    path: "tsconfig.json",
                    contents: r#"{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2020"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"]
}
"#,
                },
                TemplateFile {
                    path: "vite.config.ts",
                    contents: r#"import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
});
"#,
                },
                TemplateFile {
                    path: ".gitignore",
                    contents: r#"node_modules/
dist/
.env
"#,
                },
            ],
        },
        Template {
            name: "nextjs",
            description: "Next.js TypeScript app router project",
            create_python_venv: false,
            next_steps: vec!["cd {{project_name}}", "npm install", "npm run dev"],
            files: vec![
                TemplateFile {
                    path: "package.json",
                    contents: r#"{
  "name": "{{package_name}}",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "next": "^16.0.8",
    "react": "^19.2.1",
    "react-dom": "^19.2.1"
  },
  "devDependencies": {
    "@types/node": "^24.10.1",
    "@types/react": "^19.2.7",
    "@types/react-dom": "^19.2.3",
    "typescript": "^5.9.3"
  }
}
"#,
                },
                TemplateFile {
                    path: "app/layout.tsx",
                    contents: r#"import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "{{project_name}}",
  description: "Generated by CX Terminal",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
"#,
                },
                TemplateFile {
                    path: "app/page.tsx",
                    contents: r#"export default function Home() {
  return (
    <main>
      <h1>{{project_name}}</h1>
      <p>Next.js project generated by CX Terminal.</p>
    </main>
  );
}
"#,
                },
                TemplateFile {
                    path: "app/globals.css",
                    contents: r#"body {
  margin: 0;
  color: #18212f;
  background: #f6f8fb;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
}

main {
  display: grid;
  min-height: 100vh;
  place-content: center;
  text-align: center;
}
"#,
                },
                TemplateFile {
                    path: "next.config.js",
                    contents: r#"/** @type {import('next').NextConfig} */
const nextConfig = {};

module.exports = nextConfig;
"#,
                },
                TemplateFile {
                    path: "tsconfig.json",
                    contents: r#"{
  "compilerOptions": {
    "target": "es5",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
"#,
                },
                TemplateFile {
                    path: ".gitignore",
                    contents: r#"node_modules/
.next/
out/
.env
"#,
                },
            ],
        },
        Template {
            name: "fastapi",
            description: "FastAPI service with app/main.py and requirements.txt",
            create_python_venv: false,
            next_steps: vec![
                "cd {{project_name}}",
                "python3 -m venv .venv && source .venv/bin/activate",
                "pip install -r requirements.txt",
                "uvicorn app.main:app --reload",
            ],
            files: vec![
                TemplateFile {
                    path: "pyproject.toml",
                    contents: r#"[project]
name = "{{package_name}}"
version = "0.1.0"
description = "A FastAPI service generated by CX Terminal"
requires-python = ">=3.10"
dependencies = ["fastapi", "uvicorn[standard]"]
"#,
                },
                TemplateFile {
                    path: "requirements.txt",
                    contents: r#"fastapi
uvicorn[standard]
"#,
                },
                TemplateFile {
                    path: "app/__init__.py",
                    contents: "",
                },
                TemplateFile {
                    path: "app/main.py",
                    contents: r#"from fastapi import FastAPI

app = FastAPI(title="{{project_name}}")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Hello from {{project_name}}!"}
"#,
                },
                TemplateFile {
                    path: ".gitignore",
                    contents: r#".venv/
__pycache__/
*.pyc
.pytest_cache/
"#,
                },
            ],
        },
        Template {
            name: "go",
            description: "Go module with go.mod and main.go",
            create_python_venv: false,
            next_steps: vec!["cd {{project_name}}", "go run ."],
            files: vec![
                TemplateFile {
                    path: "go.mod",
                    contents: r#"module {{go_module}}

go 1.22
"#,
                },
                TemplateFile {
                    path: "main.go",
                    contents: r#"package main

import "fmt"

func main() {
	fmt.Println("Hello from {{project_name}}!")
}
"#,
                },
                TemplateFile {
                    path: ".gitignore",
                    contents: r#"bin/
"#,
                },
            ],
        },
        Template {
            name: "docker",
            description: "Containerized app with Dockerfile and compose file",
            create_python_venv: false,
            next_steps: vec!["cd {{project_name}}", "docker compose up --build"],
            files: vec![
                TemplateFile {
                    path: "Dockerfile",
                    contents: r#"FROM alpine:3.20

WORKDIR /app
COPY app.sh /app/app.sh
RUN chmod +x /app/app.sh

CMD ["/app/app.sh"]
"#,
                },
                TemplateFile {
                    path: "docker-compose.yml",
                    contents: r#"services:
  {{python_module}}:
    build: .
    container_name: {{package_name}}
"#,
                },
                TemplateFile {
                    path: "app.sh",
                    contents: r#"#!/usr/bin/env sh
set -eu

echo "Hello from {{project_name}}!"
"#,
                },
                TemplateFile {
                    path: ".dockerignore",
                    contents: r#".git
node_modules
.venv
"#,
                },
                TemplateFile {
                    path: "README.md",
                    contents: r#"# {{project_name}}

Generated with `cx new docker`.

```bash
docker compose up --build
```
"#,
                },
            ],
        },
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn required_templates_are_registered() {
        let names = templates()
            .into_iter()
            .map(|template| template.name)
            .collect::<Vec<_>>();

        for expected in [
            "python", "rust", "node", "react", "nextjs", "fastapi", "go", "docker",
        ] {
            assert!(names.contains(&expected), "missing template {expected}");
        }
    }

    #[test]
    fn project_names_reject_paths() {
        assert!(validate_project_name("app").is_ok());
        assert!(validate_project_name("../app").is_err());
        assert!(validate_project_name("nested/app").is_err());
        assert!(validate_project_name(".").is_err());
        assert!(validate_project_name("..").is_err());
        assert!(validate_project_name("").is_err());
    }

    #[test]
    fn context_sanitizes_language_identifiers() {
        let context = TemplateContext::new("My-App.2026");

        assert_eq!(context.package_name, "my-app-2026");
        assert_eq!(context.rust_crate, "my_app_2026");
        assert_eq!(context.python_module, "my_app_2026");
        assert_eq!(context.go_module, "example.com/my_app_2026");
    }

    #[test]
    fn all_templates_write_files_without_unrendered_placeholders() {
        let root = unique_test_dir();
        let context = TemplateContext::new("demo-app");

        for template in templates() {
            let target = root.join(template.name);
            ensure_target_directory_is_ready(&target).unwrap();
            write_template(&target, &template, &context).unwrap();

            for file in template.files.iter() {
                let output_path = target.join(render(file.path, &context));
                assert!(
                    output_path.exists(),
                    "expected {} to be written",
                    output_path.display()
                );

                let contents = fs::read_to_string(&output_path).unwrap();
                assert!(
                    !contents.contains("{{"),
                    "unrendered placeholder in {}",
                    output_path.display()
                );
            }
        }

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn default_template_accepts_name_flag() {
        let root = unique_test_dir();
        let command = NewCommand {
            template: "default".to_string(),
            project_name: None,
            name: Some("demo-app".to_string()),
            dir: Some(root.display().to_string()),
            list: false,
        };

        command.run().unwrap();

        assert!(root.join("demo-app").exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn rust_template_writes_expected_files() {
        let root = unique_test_dir();
        let template = find_template("rust").unwrap();
        let context = TemplateContext::new("demo-app");
        let target = root.join("demo-app");

        ensure_target_directory_is_ready(&target).unwrap();
        write_template(&target, &template, &context).unwrap();

        assert!(target.join("Cargo.toml").exists());
        assert!(target.join("src/main.rs").exists());
        assert!(fs::read_to_string(target.join("Cargo.toml"))
            .unwrap()
            .contains("name = \"demo-app\""));

        let _ = fs::remove_dir_all(root);
    }

    fn unique_test_dir() -> PathBuf {
        let mut dir = std::env::temp_dir();
        dir.push(format!(
            "cx-new-test-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        dir
    }
}
