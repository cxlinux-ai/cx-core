//! Workflow storage and persistence
//!
//! Manages saving and loading workflows from disk.
//! Workflows are stored as individual JSON files in ~/.config/cx-terminal/workflows/

use super::{Workflow, WorkflowError};
use std::collections::HashMap;
use std::fs::{self, File};
use std::io::{BufReader, BufWriter};
use std::path::{Path, PathBuf};
use uuid::Uuid;

/// Default workflows directory
const WORKFLOWS_DIR: &str = "workflows";
/// File extension for workflow files
const WORKFLOW_EXT: &str = "json";
/// Index file name
const INDEX_FILE: &str = "_index.json";

/// Storage manager for workflows
#[derive(Debug)]
pub struct WorkflowStorage {
    /// Base directory for workflow storage
    base_dir: PathBuf,
    /// Cached workflows (id -> workflow)
    cache: HashMap<Uuid, Workflow>,
    /// Whether the cache is loaded
    cache_loaded: bool,
}

impl WorkflowStorage {
    /// Create a new storage manager with the default directory
    pub fn new() -> Self {
        let base_dir = Self::default_dir();
        Self {
            base_dir,
            cache: HashMap::new(),
            cache_loaded: false,
        }
    }

    /// Create a storage manager with a custom directory
    pub fn with_dir(dir: PathBuf) -> Self {
        Self {
            base_dir: dir,
            cache: HashMap::new(),
            cache_loaded: false,
        }
    }

    /// Get the default workflows directory
    pub fn default_dir() -> PathBuf {
        dirs_next::config_dir()
            .unwrap_or_else(|| PathBuf::from(".config"))
            .join("cx-terminal")
            .join(WORKFLOWS_DIR)
    }

    /// Ensure the storage directory exists
    pub fn ensure_dir(&self) -> Result<(), WorkflowError> {
        if !self.base_dir.exists() {
            fs::create_dir_all(&self.base_dir)?;
        }
        Ok(())
    }

    /// Get the path for a workflow file
    fn workflow_path(&self, id: &Uuid) -> PathBuf {
        self.base_dir.join(format!("{}.{}", id, WORKFLOW_EXT))
    }

    /// Load all workflows from disk
    pub fn load_all(&mut self) -> Result<Vec<Workflow>, WorkflowError> {
        self.ensure_dir()?;
        self.cache.clear();

        let mut workflows = Vec::new();

        for entry in fs::read_dir(&self.base_dir)? {
            let entry = entry?;
            let path = entry.path();

            if path.extension().and_then(|s| s.to_str()) == Some(WORKFLOW_EXT) {
                // Skip the index file
                if path.file_stem().and_then(|s| s.to_str()) == Some("_index") {
                    continue;
                }

                match self.load_from_file(&path) {
                    Ok(workflow) => {
                        self.cache.insert(workflow.id, workflow.clone());
                        workflows.push(workflow);
                    }
                    Err(e) => {
                        log::warn!("Failed to load workflow from {:?}: {}", path, e);
                    }
                }
            }
        }

        self.cache_loaded = true;
        Ok(workflows)
    }

    /// Load a single workflow from file
    fn load_from_file(&self, path: &Path) -> Result<Workflow, WorkflowError> {
        let file = File::open(path)?;
        let reader = BufReader::new(file);
        let workflow: Workflow = serde_json::from_reader(reader)?;
        Ok(workflow)
    }

    /// Save a workflow to disk
    pub fn save(&mut self, workflow: &Workflow) -> Result<(), WorkflowError> {
        self.ensure_dir()?;

        let path = self.workflow_path(&workflow.id);
        let file = File::create(&path)?;
        let writer = BufWriter::new(file);

        serde_json::to_writer_pretty(writer, workflow)?;

        // Update cache
        self.cache.insert(workflow.id, workflow.clone());

        Ok(())
    }

    /// Delete a workflow from disk
    pub fn delete(&mut self, id: &Uuid) -> Result<(), WorkflowError> {
        let path = self.workflow_path(id);

        if path.exists() {
            fs::remove_file(&path)?;
        }

        self.cache.remove(id);

        Ok(())
    }

    /// Get a workflow by ID
    pub fn get(&mut self, id: &Uuid) -> Result<Option<Workflow>, WorkflowError> {
        // Check cache first
        if let Some(workflow) = self.cache.get(id) {
            return Ok(Some(workflow.clone()));
        }

        // Try loading from file
        let path = self.workflow_path(id);
        if path.exists() {
            let workflow = self.load_from_file(&path)?;
            self.cache.insert(*id, workflow.clone());
            Ok(Some(workflow))
        } else {
            Ok(None)
        }
    }

    /// Get a workflow by name
    pub fn get_by_name(&mut self, name: &str) -> Result<Option<Workflow>, WorkflowError> {
        if !self.cache_loaded {
            self.load_all()?;
        }

        Ok(self.cache.values().find(|w| w.name == name).cloned())
    }

    /// Search workflows by name or tags
    pub fn search(&mut self, query: &str) -> Result<Vec<Workflow>, WorkflowError> {
        if !self.cache_loaded {
            self.load_all()?;
        }

        let query_lower = query.to_lowercase();

        let results: Vec<_> = self
            .cache
            .values()
            .filter(|w| {
                w.name.to_lowercase().contains(&query_lower)
                    || w.description.to_lowercase().contains(&query_lower)
                    || w.tags.iter().any(|t| t.to_lowercase().contains(&query_lower))
            })
            .cloned()
            .collect();

        Ok(results)
    }

    /// List all workflows
    pub fn list(&mut self) -> Result<Vec<Workflow>, WorkflowError> {
        if !self.cache_loaded {
            self.load_all()?;
        }

        let mut workflows: Vec<_> = self.cache.values().cloned().collect();
        workflows.sort_by(|a, b| a.name.cmp(&b.name));
        Ok(workflows)
    }

    /// List favorite workflows
    pub fn list_favorites(&mut self) -> Result<Vec<Workflow>, WorkflowError> {
        if !self.cache_loaded {
            self.load_all()?;
        }

        let mut workflows: Vec<_> = self
            .cache
            .values()
            .filter(|w| w.favorite)
            .cloned()
            .collect();

        workflows.sort_by(|a, b| a.name.cmp(&b.name));
        Ok(workflows)
    }

    /// List recent workflows
    pub fn list_recent(&mut self, limit: usize) -> Result<Vec<Workflow>, WorkflowError> {
        if !self.cache_loaded {
            self.load_all()?;
        }

        let mut workflows: Vec<_> = self
            .cache
            .values()
            .filter(|w| w.last_run.is_some())
            .cloned()
            .collect();

        workflows.sort_by(|a, b| b.last_run.cmp(&a.last_run));
        workflows.truncate(limit);
        Ok(workflows)
    }

    /// List frequently used workflows
    pub fn list_frequent(&mut self, limit: usize) -> Result<Vec<Workflow>, WorkflowError> {
        if !self.cache_loaded {
            self.load_all()?;
        }

        let mut workflows: Vec<_> = self
            .cache
            .values()
            .filter(|w| w.run_count > 0)
            .cloned()
            .collect();

        workflows.sort_by(|a, b| b.run_count.cmp(&a.run_count));
        workflows.truncate(limit);
        Ok(workflows)
    }

    /// List workflows by tag
    pub fn list_by_tag(&mut self, tag: &str) -> Result<Vec<Workflow>, WorkflowError> {
        if !self.cache_loaded {
            self.load_all()?;
        }

        let tag_lower = tag.to_lowercase();
        let workflows: Vec<_> = self
            .cache
            .values()
            .filter(|w| w.tags.iter().any(|t| t.to_lowercase() == tag_lower))
            .cloned()
            .collect();

        Ok(workflows)
    }

    /// Get all unique tags
    pub fn all_tags(&mut self) -> Result<Vec<String>, WorkflowError> {
        if !self.cache_loaded {
            self.load_all()?;
        }

        let mut tags: Vec<_> = self
            .cache
            .values()
            .flat_map(|w| w.tags.iter())
            .cloned()
            .collect();

        tags.sort();
        tags.dedup();
        Ok(tags)
    }

    /// Import a workflow from a file
    pub fn import(&mut self, path: &Path) -> Result<Workflow, WorkflowError> {
        let workflow = self.load_from_file(path)?;

        // Check for duplicate
        if self.cache.contains_key(&workflow.id) {
            // Generate new ID for the import
            let mut imported = workflow.clone();
            imported.id = Uuid::new_v4();
            imported.name = format!("{} (imported)", imported.name);
            self.save(&imported)?;
            Ok(imported)
        } else {
            self.save(&workflow)?;
            Ok(workflow)
        }
    }

    /// Export a workflow to a file
    pub fn export(&self, id: &Uuid, path: &Path) -> Result<(), WorkflowError> {
        let workflow = self
            .cache
            .get(id)
            .ok_or_else(|| WorkflowError::NotFound(id.to_string()))?;

        let file = File::create(path)?;
        let writer = BufWriter::new(file);
        serde_json::to_writer_pretty(writer, workflow)?;

        Ok(())
    }

    /// Duplicate a workflow
    pub fn duplicate(&mut self, id: &Uuid) -> Result<Workflow, WorkflowError> {
        let original = self
            .get(id)?
            .ok_or_else(|| WorkflowError::NotFound(id.to_string()))?;

        let mut copy = original.clone();
        copy.id = Uuid::new_v4();
        copy.name = format!("{} (copy)", original.name);
        copy.created_at = chrono::Utc::now();
        copy.updated_at = chrono::Utc::now();
        copy.last_run = None;
        copy.run_count = 0;

        self.save(&copy)?;
        Ok(copy)
    }

    /// Get workflow statistics
    pub fn stats(&mut self) -> Result<WorkflowStats, WorkflowError> {
        if !self.cache_loaded {
            self.load_all()?;
        }

        let total = self.cache.len();
        let favorites = self.cache.values().filter(|w| w.favorite).count();
        let total_runs: u32 = self.cache.values().map(|w| w.run_count).sum();
        let most_used = self
            .cache
            .values()
            .max_by_key(|w| w.run_count)
            .map(|w| w.name.clone());

        Ok(WorkflowStats {
            total_workflows: total,
            favorite_count: favorites,
            total_runs,
            most_used,
        })
    }

    /// Clear the cache
    pub fn clear_cache(&mut self) {
        self.cache.clear();
        self.cache_loaded = false;
    }

    /// Get workflows with shortcuts
    pub fn get_shortcuts(&mut self) -> Result<HashMap<String, Uuid>, WorkflowError> {
        if !self.cache_loaded {
            self.load_all()?;
        }

        let shortcuts: HashMap<_, _> = self
            .cache
            .values()
            .filter_map(|w| w.shortcut.as_ref().map(|s| (s.clone(), w.id)))
            .collect();

        Ok(shortcuts)
    }
}

impl Default for WorkflowStorage {
    fn default() -> Self {
        Self::new()
    }
}

/// Statistics about stored workflows
#[derive(Debug, Clone)]
pub struct WorkflowStats {
    /// Total number of workflows
    pub total_workflows: usize,
    /// Number of favorite workflows
    pub favorite_count: usize,
    /// Total number of runs across all workflows
    pub total_runs: u32,
    /// Name of the most used workflow
    pub most_used: Option<String>,
}

/// Builder for creating workflows interactively
#[derive(Debug, Default)]
pub struct WorkflowBuilder {
    workflow: Workflow,
}

impl WorkflowBuilder {
    /// Create a new workflow builder
    pub fn new(name: &str) -> Self {
        Self {
            workflow: Workflow::new(name),
        }
    }

    /// Set the description
    pub fn description(mut self, desc: &str) -> Self {
        self.workflow.description = desc.to_string();
        self
    }

    /// Add a command step
    pub fn add_command(mut self, command: &str) -> Self {
        self.workflow.add_step(super::WorkflowStep::new(command));
        self
    }

    /// Add a step
    pub fn add_step(mut self, step: super::WorkflowStep) -> Self {
        self.workflow.add_step(step);
        self
    }

    /// Add a tag
    pub fn tag(mut self, tag: &str) -> Self {
        self.workflow.tags.push(tag.to_string());
        self
    }

    /// Set as favorite
    pub fn favorite(mut self) -> Self {
        self.workflow.favorite = true;
        self
    }

    /// Set a shortcut
    pub fn shortcut(mut self, shortcut: &str) -> Self {
        self.workflow.shortcut = Some(shortcut.to_string());
        self
    }

    /// Build the workflow
    pub fn build(self) -> Workflow {
        self.workflow
    }

    /// Build and save the workflow
    pub fn save(self, storage: &mut WorkflowStorage) -> Result<Workflow, WorkflowError> {
        let workflow = self.build();
        storage.save(&workflow)?;
        Ok(workflow)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_storage_save_load() {
        let dir = tempdir().unwrap();
        let mut storage = WorkflowStorage::with_dir(dir.path().to_path_buf());

        let workflow = Workflow::from_commands("Test", vec!["echo hello"]);
        storage.save(&workflow).unwrap();

        let loaded = storage.get(&workflow.id).unwrap().unwrap();
        assert_eq!(loaded.name, "Test");
        assert_eq!(loaded.steps.len(), 1);
    }

    #[test]
    fn test_storage_delete() {
        let dir = tempdir().unwrap();
        let mut storage = WorkflowStorage::with_dir(dir.path().to_path_buf());

        let workflow = Workflow::new("Test");
        storage.save(&workflow).unwrap();

        storage.delete(&workflow.id).unwrap();

        let result = storage.get(&workflow.id).unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn test_storage_search() {
        let dir = tempdir().unwrap();
        let mut storage = WorkflowStorage::with_dir(dir.path().to_path_buf());

        let mut w1 = Workflow::new("Build Project");
        w1.tags = vec!["rust".to_string()];
        storage.save(&w1).unwrap();

        let mut w2 = Workflow::new("Deploy App");
        w2.tags = vec!["deploy".to_string()];
        storage.save(&w2).unwrap();

        let results = storage.search("build").unwrap();
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].name, "Build Project");

        let results = storage.search("rust").unwrap();
        assert_eq!(results.len(), 1);
    }

    #[test]
    fn test_workflow_builder() {
        let workflow = WorkflowBuilder::new("Deploy")
            .description("Deploy to production")
            .add_command("cargo build --release")
            .add_command("./deploy.sh")
            .tag("deploy")
            .tag("production")
            .favorite()
            .build();

        assert_eq!(workflow.name, "Deploy");
        assert_eq!(workflow.steps.len(), 2);
        assert_eq!(workflow.tags.len(), 2);
        assert!(workflow.favorite);
    }
}
