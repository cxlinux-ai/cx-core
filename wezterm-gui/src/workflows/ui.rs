//! Workflow UI components
//!
//! Provides UI for:
//! - Workflow picker (Ctrl+Shift+W)
//! - Create workflow from history
//! - Edit workflow
//! - Variable input dialog

use super::storage::WorkflowStorage;
use super::{Workflow, WorkflowStep, WorkflowVariable};
use std::collections::HashMap;
use uuid::Uuid;

/// Filter mode for the workflow picker
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum WorkflowFilter {
    /// Show all workflows
    #[default]
    All,
    /// Show only favorites
    Favorites,
    /// Show recently used
    Recent,
    /// Show frequently used
    Frequent,
    /// Filter by tag
    Tag,
}

/// State for the workflow picker UI
#[derive(Debug)]
pub struct WorkflowPickerState {
    /// Current search query
    pub query: String,
    /// Current filter mode
    pub filter: WorkflowFilter,
    /// Current tag filter (if filter mode is Tag)
    pub tag_filter: Option<String>,
    /// List of workflows matching the filter
    pub workflows: Vec<WorkflowListItem>,
    /// Currently selected index
    pub selected_index: usize,
    /// Whether the picker is visible
    pub visible: bool,
    /// All available tags
    pub available_tags: Vec<String>,
}

impl Default for WorkflowPickerState {
    fn default() -> Self {
        Self {
            query: String::new(),
            filter: WorkflowFilter::All,
            tag_filter: None,
            workflows: Vec::new(),
            selected_index: 0,
            visible: false,
            available_tags: Vec::new(),
        }
    }
}

impl WorkflowPickerState {
    /// Create a new picker state
    pub fn new() -> Self {
        Self::default()
    }

    /// Show the picker
    pub fn show(&mut self) {
        self.visible = true;
        self.query.clear();
        self.selected_index = 0;
    }

    /// Hide the picker
    pub fn hide(&mut self) {
        self.visible = false;
    }

    /// Refresh the workflow list from storage
    pub fn refresh(&mut self, storage: &mut WorkflowStorage) {
        let workflows_result = match self.filter {
            WorkflowFilter::All => storage.list(),
            WorkflowFilter::Favorites => storage.list_favorites(),
            WorkflowFilter::Recent => storage.list_recent(20),
            WorkflowFilter::Frequent => storage.list_frequent(20),
            WorkflowFilter::Tag => {
                if let Some(ref tag) = self.tag_filter {
                    storage.list_by_tag(tag)
                } else {
                    storage.list()
                }
            }
        };

        self.workflows = match workflows_result {
            Ok(workflows) => self.filter_by_query(workflows),
            Err(_) => Vec::new(),
        };

        // Update available tags
        if let Ok(tags) = storage.all_tags() {
            self.available_tags = tags;
        }

        // Clamp selected index
        if !self.workflows.is_empty() && self.selected_index >= self.workflows.len() {
            self.selected_index = self.workflows.len() - 1;
        }
    }

    /// Filter workflows by the current search query
    fn filter_by_query(&self, workflows: Vec<Workflow>) -> Vec<WorkflowListItem> {
        let query_lower = self.query.to_lowercase();

        workflows
            .into_iter()
            .filter(|w| {
                if self.query.is_empty() {
                    true
                } else {
                    w.name.to_lowercase().contains(&query_lower)
                        || w.description.to_lowercase().contains(&query_lower)
                        || w.tags.iter().any(|t| t.to_lowercase().contains(&query_lower))
                }
            })
            .map(WorkflowListItem::from)
            .collect()
    }

    /// Handle character input in search
    pub fn on_char(&mut self, c: char) {
        self.query.push(c);
    }

    /// Handle backspace in search
    pub fn on_backspace(&mut self) {
        self.query.pop();
    }

    /// Clear the search query
    pub fn clear_query(&mut self) {
        self.query.clear();
    }

    /// Move selection up
    pub fn select_previous(&mut self) {
        if !self.workflows.is_empty() && self.selected_index > 0 {
            self.selected_index -= 1;
        }
    }

    /// Move selection down
    pub fn select_next(&mut self) {
        if !self.workflows.is_empty() && self.selected_index < self.workflows.len() - 1 {
            self.selected_index += 1;
        }
    }

    /// Get the currently selected workflow
    pub fn selected(&self) -> Option<&WorkflowListItem> {
        self.workflows.get(self.selected_index)
    }

    /// Cycle through filter modes
    pub fn cycle_filter(&mut self) {
        self.filter = match self.filter {
            WorkflowFilter::All => WorkflowFilter::Favorites,
            WorkflowFilter::Favorites => WorkflowFilter::Recent,
            WorkflowFilter::Recent => WorkflowFilter::Frequent,
            WorkflowFilter::Frequent => WorkflowFilter::All,
            WorkflowFilter::Tag => WorkflowFilter::All,
        };
        self.selected_index = 0;
    }

    /// Set filter to a specific tag
    pub fn filter_by_tag(&mut self, tag: &str) {
        self.filter = WorkflowFilter::Tag;
        self.tag_filter = Some(tag.to_string());
        self.selected_index = 0;
    }
}

/// Item in the workflow list
#[derive(Debug, Clone)]
pub struct WorkflowListItem {
    /// Workflow ID
    pub id: Uuid,
    /// Workflow name
    pub name: String,
    /// Workflow description
    pub description: String,
    /// Whether it's a favorite
    pub favorite: bool,
    /// Tags
    pub tags: Vec<String>,
    /// Number of steps
    pub step_count: usize,
    /// Run count
    pub run_count: u32,
    /// Shortcut if any
    pub shortcut: Option<String>,
}

impl From<Workflow> for WorkflowListItem {
    fn from(w: Workflow) -> Self {
        Self {
            id: w.id,
            name: w.name,
            description: w.description,
            favorite: w.favorite,
            tags: w.tags,
            step_count: w.steps.len(),
            run_count: w.run_count,
            shortcut: w.shortcut,
        }
    }
}

/// State for the workflow editor UI
#[derive(Debug, Default)]
pub struct WorkflowEditorState {
    /// The workflow being edited
    pub workflow: Option<Workflow>,
    /// Currently selected step index
    pub selected_step: usize,
    /// Whether we're editing the name
    pub editing_name: bool,
    /// Whether we're editing the description
    pub editing_description: bool,
    /// Whether we're editing a step command
    pub editing_step: Option<usize>,
    /// Temporary edit buffer
    pub edit_buffer: String,
    /// Whether the editor is visible
    pub visible: bool,
    /// Whether there are unsaved changes
    pub dirty: bool,
}

impl WorkflowEditorState {
    /// Create a new editor state
    pub fn new() -> Self {
        Self::default()
    }

    /// Open a workflow for editing
    pub fn open(&mut self, workflow: Workflow) {
        self.workflow = Some(workflow);
        self.selected_step = 0;
        self.editing_name = false;
        self.editing_description = false;
        self.editing_step = None;
        self.edit_buffer.clear();
        self.visible = true;
        self.dirty = false;
    }

    /// Create a new workflow
    pub fn create_new(&mut self) {
        self.open(Workflow::new("New Workflow"));
        self.editing_name = true;
        self.edit_buffer = "New Workflow".to_string();
    }

    /// Close the editor
    pub fn close(&mut self) {
        self.workflow = None;
        self.visible = false;
    }

    /// Start editing the name
    pub fn edit_name(&mut self) {
        if let Some(ref workflow) = self.workflow {
            self.editing_name = true;
            self.edit_buffer = workflow.name.clone();
        }
    }

    /// Start editing the description
    pub fn edit_description(&mut self) {
        if let Some(ref workflow) = self.workflow {
            self.editing_description = true;
            self.edit_buffer = workflow.description.clone();
        }
    }

    /// Start editing a step
    pub fn edit_step(&mut self, index: usize) {
        if let Some(ref workflow) = self.workflow {
            if let Some(step) = workflow.steps.get(index) {
                self.editing_step = Some(index);
                self.edit_buffer = step.command.clone();
            }
        }
    }

    /// Confirm the current edit
    pub fn confirm_edit(&mut self) {
        if let Some(ref mut workflow) = self.workflow {
            if self.editing_name {
                workflow.name = self.edit_buffer.clone();
                self.editing_name = false;
                self.dirty = true;
            } else if self.editing_description {
                workflow.description = self.edit_buffer.clone();
                self.editing_description = false;
                self.dirty = true;
            } else if let Some(index) = self.editing_step {
                if let Some(step) = workflow.steps.get_mut(index) {
                    step.command = self.edit_buffer.clone();
                    self.dirty = true;
                }
                self.editing_step = None;
            }
        }
        self.edit_buffer.clear();
    }

    /// Cancel the current edit
    pub fn cancel_edit(&mut self) {
        self.editing_name = false;
        self.editing_description = false;
        self.editing_step = None;
        self.edit_buffer.clear();
    }

    /// Add a new step
    pub fn add_step(&mut self, command: &str) {
        if let Some(ref mut workflow) = self.workflow {
            workflow.add_step(WorkflowStep::new(command));
            self.selected_step = workflow.steps.len() - 1;
            self.dirty = true;
        }
    }

    /// Remove the selected step
    pub fn remove_step(&mut self) {
        if let Some(ref mut workflow) = self.workflow {
            if workflow.steps.len() > 1 {
                workflow.remove_step(self.selected_step);
                if self.selected_step >= workflow.steps.len() {
                    self.selected_step = workflow.steps.len() - 1;
                }
                self.dirty = true;
            }
        }
    }

    /// Move selected step up
    pub fn move_step_up(&mut self) {
        if let Some(ref mut workflow) = self.workflow {
            if self.selected_step > 0 {
                workflow.steps.swap(self.selected_step, self.selected_step - 1);
                self.selected_step -= 1;
                self.dirty = true;
            }
        }
    }

    /// Move selected step down
    pub fn move_step_down(&mut self) {
        if let Some(ref mut workflow) = self.workflow {
            if self.selected_step < workflow.steps.len() - 1 {
                workflow.steps.swap(self.selected_step, self.selected_step + 1);
                self.selected_step += 1;
                self.dirty = true;
            }
        }
    }

    /// Toggle favorite status
    pub fn toggle_favorite(&mut self) {
        if let Some(ref mut workflow) = self.workflow {
            workflow.favorite = !workflow.favorite;
            self.dirty = true;
        }
    }

    /// Add a tag
    pub fn add_tag(&mut self, tag: &str) {
        if let Some(ref mut workflow) = self.workflow {
            if !workflow.tags.contains(&tag.to_string()) {
                workflow.tags.push(tag.to_string());
                self.dirty = true;
            }
        }
    }

    /// Remove a tag
    pub fn remove_tag(&mut self, tag: &str) {
        if let Some(ref mut workflow) = self.workflow {
            workflow.tags.retain(|t| t != tag);
            self.dirty = true;
        }
    }
}

/// State for variable input dialog
#[derive(Debug, Default)]
pub struct VariableInputState {
    /// The workflow being configured
    pub workflow_id: Option<Uuid>,
    /// Variables to collect
    pub variables: Vec<VariableInputItem>,
    /// Currently selected variable index
    pub selected_index: usize,
    /// Whether we're editing a value
    pub editing: bool,
    /// Current edit buffer
    pub edit_buffer: String,
    /// Whether the dialog is visible
    pub visible: bool,
}

impl VariableInputState {
    /// Create a new variable input state
    pub fn new() -> Self {
        Self::default()
    }

    /// Open the dialog for a workflow
    pub fn open(&mut self, workflow: &Workflow) {
        self.workflow_id = Some(workflow.id);
        self.variables = workflow
            .variables
            .iter()
            .map(|(name, var)| VariableInputItem {
                name: name.clone(),
                description: var.description.clone(),
                value: var.default_value.clone(),
                required: var.required,
                options: var.options.clone(),
            })
            .collect();
        self.selected_index = 0;
        self.editing = false;
        self.edit_buffer.clear();
        self.visible = true;
    }

    /// Close the dialog
    pub fn close(&mut self) {
        self.workflow_id = None;
        self.variables.clear();
        self.visible = false;
    }

    /// Start editing the current variable
    pub fn start_edit(&mut self) {
        if let Some(var) = self.variables.get(self.selected_index) {
            self.editing = true;
            self.edit_buffer = var.value.clone();
        }
    }

    /// Confirm the current edit
    pub fn confirm_edit(&mut self) {
        if self.editing {
            if let Some(var) = self.variables.get_mut(self.selected_index) {
                var.value = self.edit_buffer.clone();
            }
            self.editing = false;
            self.edit_buffer.clear();
        }
    }

    /// Cancel the current edit
    pub fn cancel_edit(&mut self) {
        self.editing = false;
        self.edit_buffer.clear();
    }

    /// Move selection up
    pub fn select_previous(&mut self) {
        if self.selected_index > 0 {
            self.selected_index -= 1;
        }
    }

    /// Move selection down
    pub fn select_next(&mut self) {
        if self.selected_index < self.variables.len().saturating_sub(1) {
            self.selected_index += 1;
        }
    }

    /// Get all variable values
    pub fn get_values(&self) -> HashMap<String, String> {
        self.variables
            .iter()
            .map(|v| (v.name.clone(), v.value.clone()))
            .collect()
    }

    /// Check if all required variables have values
    pub fn is_valid(&self) -> bool {
        self.variables
            .iter()
            .filter(|v| v.required)
            .all(|v| !v.value.is_empty())
    }
}

/// Item in the variable input dialog
#[derive(Debug, Clone)]
pub struct VariableInputItem {
    /// Variable name
    pub name: String,
    /// Variable description
    pub description: String,
    /// Current value
    pub value: String,
    /// Whether the variable is required
    pub required: bool,
    /// Options for select-type variables
    pub options: Option<Vec<String>>,
}

/// State for the "create from history" UI
#[derive(Debug, Default)]
pub struct CreateFromHistoryState {
    /// Available history entries
    pub history: Vec<String>,
    /// Selected entries (indices)
    pub selected: Vec<usize>,
    /// Current cursor position
    pub cursor: usize,
    /// Whether the dialog is visible
    pub visible: bool,
    /// Workflow name input
    pub name: String,
    /// Whether we're editing the name
    pub editing_name: bool,
}

impl CreateFromHistoryState {
    /// Create a new state
    pub fn new() -> Self {
        Self::default()
    }

    /// Open the dialog with history
    pub fn open(&mut self, history: Vec<String>) {
        self.history = history;
        self.selected.clear();
        self.cursor = 0;
        self.visible = true;
        self.name = "New Workflow".to_string();
        self.editing_name = false;
    }

    /// Close the dialog
    pub fn close(&mut self) {
        self.history.clear();
        self.selected.clear();
        self.visible = false;
    }

    /// Toggle selection of current item
    pub fn toggle_selection(&mut self) {
        if let Some(pos) = self.selected.iter().position(|&x| x == self.cursor) {
            self.selected.remove(pos);
        } else {
            self.selected.push(self.cursor);
        }
    }

    /// Move cursor up
    pub fn cursor_up(&mut self) {
        if self.cursor > 0 {
            self.cursor -= 1;
        }
    }

    /// Move cursor down
    pub fn cursor_down(&mut self) {
        if self.cursor < self.history.len().saturating_sub(1) {
            self.cursor += 1;
        }
    }

    /// Get selected commands in order
    pub fn get_selected_commands(&self) -> Vec<String> {
        let mut indices = self.selected.clone();
        indices.sort();
        indices
            .into_iter()
            .filter_map(|i| self.history.get(i).cloned())
            .collect()
    }

    /// Create the workflow
    pub fn create_workflow(&self) -> Workflow {
        let selected_commands = self.get_selected_commands();
        let commands: Vec<&str> = selected_commands
            .iter()
            .map(|s| s.as_str())
            .collect();

        Workflow::from_commands(&self.name, commands)
    }

    /// Check if any commands are selected
    pub fn has_selection(&self) -> bool {
        !self.selected.is_empty()
    }
}

/// Keyboard shortcuts for workflow operations
pub mod shortcuts {
    /// Open workflow picker
    pub const WORKFLOW_PICKER: &str = "Ctrl+Shift+W";
    /// Save selection as workflow
    pub const SAVE_AS_WORKFLOW: &str = "Ctrl+Shift+S";
    /// Run last workflow
    pub const RUN_LAST_WORKFLOW: &str = "Ctrl+Shift+R";
    /// Quick workflow by shortcut
    pub const QUICK_WORKFLOW_PREFIX: &str = "Ctrl+Shift+";
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_picker_state() {
        let mut state = WorkflowPickerState::new();

        state.show();
        assert!(state.visible);

        state.on_char('t');
        state.on_char('e');
        state.on_char('s');
        state.on_char('t');
        assert_eq!(state.query, "test");

        state.on_backspace();
        assert_eq!(state.query, "tes");

        state.clear_query();
        assert_eq!(state.query, "");

        state.hide();
        assert!(!state.visible);
    }

    #[test]
    fn test_editor_state() {
        let mut state = WorkflowEditorState::new();

        state.create_new();
        assert!(state.visible);
        assert!(state.workflow.is_some());
        assert!(state.editing_name);

        state.confirm_edit();
        assert!(!state.editing_name);

        state.add_step("echo test");
        assert_eq!(state.workflow.as_ref().unwrap().steps.len(), 1);

        state.close();
        assert!(!state.visible);
    }

    #[test]
    fn test_variable_input_state() {
        let mut workflow = Workflow::new("Test");
        workflow.add_variable(
            "name",
            WorkflowVariable::with_default("Name", "default"),
        );

        let mut state = VariableInputState::new();
        state.open(&workflow);

        assert!(state.visible);
        assert_eq!(state.variables.len(), 1);
        assert_eq!(state.variables[0].value, "default");

        state.start_edit();
        state.edit_buffer = "custom".to_string();
        state.confirm_edit();

        assert_eq!(state.variables[0].value, "custom");

        let values = state.get_values();
        assert_eq!(values.get("name"), Some(&"custom".to_string()));

        state.close();
        assert!(!state.visible);
    }

    #[test]
    fn test_create_from_history() {
        let mut state = CreateFromHistoryState::new();

        state.open(vec![
            "ls -la".to_string(),
            "cd /tmp".to_string(),
            "echo hello".to_string(),
        ]);

        assert!(state.visible);
        assert_eq!(state.history.len(), 3);

        state.toggle_selection(); // Select first
        state.cursor_down();
        state.cursor_down();
        state.toggle_selection(); // Select third

        assert_eq!(state.selected.len(), 2);

        let commands = state.get_selected_commands();
        assert_eq!(commands.len(), 2);
        assert_eq!(commands[0], "ls -la");
        assert_eq!(commands[1], "echo hello");

        let workflow = state.create_workflow();
        assert_eq!(workflow.steps.len(), 2);
    }
}
