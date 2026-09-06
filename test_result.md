#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  FIX10A shadow (observe-only physical match reconstruction) produced no output on a real
  production report (player "Romani"): no fix10a_* fields were written and no shadow logs were
  emitted, even though FIX10A_SHADOW_ENABLED=1 and the unified analysis was production-ready
  (status=ok, coverage_complete=true). Root cause (most plausible): server.py scheduled the
  shadow via a bare asyncio.create_task(...) with no strong reference, so the fire-and-forget
  task could be dropped/cancelled mid-run before writing. Fix is strictly shadow-only.

backend:
  - task: "FIX10A shadow task lifecycle fix (strong reference + lifecycle logging)"
    implemented: true
    working: true
    file: "backend/fix10a_shadow_runtime.py, backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: |
          Added fix10a_shadow_runtime.spawn_shadow(): keeps a strong module-level reference to
          the in-flight observe-only task in _SHADOW_TASKS, removes it via add_done_callback on
          completion (registry tracks only active tasks), and logs START/SKIP/SUCCESS/ERROR/
          CANCELLED with report_id. server.py now calls spawn_shadow(...) instead of a bare
          asyncio.create_task(run_shadow(...)). Also added skip/disabled/success/error logging
          inside run_shadow. NO changes to canonical authority (canonical_authority stays False),
          unified analysis, FIX09B/C, scoring, ratings, verified stats, tracking, identity, report
          generation, or Mongo schema (only existing fix10a_* diagnostic fields).
          Local verification (main agent): py_compile OK; new deterministic regression
          tests/test_fix10a_shadow_task_lifecycle.py 5/5 PASS; FIX10A family 225/225 PASS and
          FIX00-09+unified family 595/595 PASS (run with -o asyncio_mode=auto). The 9 async
          "failures" seen without that flag are a pre-existing async-harness (pytest-asyncio
          strict-mode late-marker) config gap affecting untouched modules too — not a regression.
        -working: true
        -agent: "testing"
        -comment: |
          VERIFIED: FIX10A shadow task lifecycle fix is working correctly.
          
          Backend Health Check (Step 1):
          - GET https://vedoscout-main.preview.emergentagent.com/api/ returned HTTP 200 ✓
          - Backend supervisor status: RUNNING (pid 263, uptime 0:18:58) ✓
          - No crash-looping detected, clean startup logs ✓
          - server.py imports cleanly with the edited spawn_shadow() call ✓
          
          Deterministic Regression Test (Step 2):
          - Command: cd /app/backend && python -m pytest tests/test_fix10a_shadow_task_lifecycle.py -v
          - Result: 5 passed in 2.03s ✓
          - All lifecycle tests passed:
            • test_task_referenced_while_running_then_removed PASSED
            • test_uncaught_exception_is_logged_and_removed PASSED
            • test_cancelled_is_logged_and_removed PASSED
            • test_shadow_only_writes_fix10a_fields PASSED
            • test_skip_path_persists_nothing PASSED
          
          Changed Module Tests (Step 3):
          - Command: cd /app/backend && python -m pytest tests/test_fix10a_shadow_runtime.py tests/test_fix10a_provider_wiring.py -o asyncio_mode=auto -v
          - Result: 7 passed in 1.84s ✓
          - All shadow runtime and provider wiring tests passed:
            • test_shadow01_default_off_does_nothing PASSED
            • test_shadow02_unready_unified_result_is_skipped PASSED
            • test_shadow03_success_persists_compact_summary_and_r2_trace PASSED
            • test_shadow04_r2_unavailable_uses_local_diagnostic_fallback PASSED
            • test_shadow05_physical_exception_is_diagnostic_and_never_raises PASSED
            • test_pw01_role_provider_result_reaches_a7_without_canonical_output PASSED
            • test_pw02_shadow_autowires_supporting_callbacks_only PASSED
          
          Conclusion: The fix successfully addresses the shadow task lifecycle bug. Tasks are now
          properly referenced during execution, removed on completion, and all lifecycle events
          (START/SKIP/SUCCESS/ERROR/CANCELLED) are logged. No regression in backend startup or
          existing functionality. FIX10A maintains observe-only status (canonical_authority=False)
          and only writes fix10a_* diagnostic fields as designed.

metadata:
  created_by: "main_agent"
  version: "1.1"
  test_sequence: 0
  run_ui: false

test_plan:
  current_focus:
    - "FIX10A shadow task lifecycle fix (strong reference + lifecycle logging)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    -agent: "main"
    -message: |
      Please verify the FIX10A shadow lifecycle fix WITHOUT running any real video analysis and
      WITHOUT any external/LLM provider calls (strict cost control). Scope:
      1) Backend health: GET {REACT_APP_BACKEND_URL}/api/ returns HTTP 200 and backend imports
         cleanly (my server.py edit is at the analysis path ~line 9228; confirm no startup regression).
      2) Run the deterministic regression: cd /app/backend && python -m pytest
         tests/test_fix10a_shadow_task_lifecycle.py -v  -> expect 5 passed. This proves: task stays
         referenced while running, is removed on completion, exceptions & cancellation are observable
         via logs, scheduling is non-blocking, and FIX10A only writes fix10a_* fields (cannot mutate
         canonical; canonical_authority stays False).
      3) Also run: cd /app/backend && python -m pytest tests/test_fix10a_shadow_runtime.py
         tests/test_fix10a_provider_wiring.py -o asyncio_mode=auto -v  -> expect all pass (these
         directly exercise the changed module). Do NOT modify code. Report pass/fail counts and any
         backend errors verbatim.
    -agent: "testing"
    -message: |
      FIX10A shadow task lifecycle fix VERIFIED successfully. All three verification steps passed:
      1) Backend health: HTTP 200, RUNNING status, no crash-looping ✓
      2) Lifecycle regression test: 5/5 passed ✓
      3) Shadow runtime & provider wiring tests: 7/7 passed ✓
      No code modifications were made. The fix correctly implements strong task references,
      lifecycle logging, and maintains observe-only behavior (canonical_authority=False).
      Ready for production deployment.