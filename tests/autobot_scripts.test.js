const assert = require("node:assert/strict");
const test = require("node:test");

const {
  AutobotLabelRegistry,
  MAX_AUTOBOT_LABELS,
  normalizeLabelName,
  trimLowSignalLabels
} = require("../.github/scripts/autobot_labels");
const {
  AutobotDeterministicScorer,
  scoreDeterministicEvidence
} = require("../.github/scripts/autobot_deterministic_scorer");
const {
  AutobotIssueClassifier,
  analyzeIssueIntake
} = require("../.github/scripts/autobot_issue_intake");
const {
  AutobotPromptBuilder,
  buildIssueSummaryArtifacts
} = require("../.github/scripts/autobot_prompts");
const {
  AutobotPullRequestAnalyzer,
  analyzePullRequestSnapshotData
} = require("../.github/scripts/autobot_pr_analysis");
const {
  AutobotProjectManager,
  resolvePrLabelDelta
} = require("../.github/scripts/autobot_project_manager");

test("label registry normalizes aliases", () => {
  assert.equal(normalizeLabelName("breaking_change"), "breaking-change");
  assert.equal(AutobotLabelRegistry.normalizeLabelName("Breaking-Changes"), "breaking-change");
});

test("label registry trims low-signal labels with version-sensitive priority", () => {
  const labels = trimLowSignalLabels([
    "documentation",
    "config",
    "bug",
    "workflow",
    "enhancement",
    "cleanup",
    "runtime",
    "security",
    "test",
    "schema",
    "api",
    "dependencies",
    "breaking_change",
    "tooling"
  ]);

  assert.ok(labels.length <= MAX_AUTOBOT_LABELS);
  assert.equal(labels[0], "breaking-change");
  assert.ok(labels.includes("security"));
  assert.ok(labels.includes("api"));
  assert.ok(!labels.includes("breaking_change"));
});

test("deterministic scorer promotes destructive public export removal to major", () => {
  const result = scoreDeterministicEvidence([{ ruleId: "removed-public-export" }]);

  assert.equal(result.semver.decision, "major");
  assert.ok(result.labelScores["breaking-change"].retained);
  assert.ok(result.emittedLabels.some((entry) => entry.label === "breaking-change"));
  assert.equal(AutobotDeterministicScorer.scoreDeterministicEvidence([{ ruleId: "removed-public-export" }]).semver.decision, "major");
});

test("issue classifier detects documentation issues from the template", () => {
  const issue = {
    title: "Documentation issue report: missing README section",
    body: [
      "Documentation issue report",
      "Link(s) to the affected documentation",
      "Detailed description of the problem",
      "The section is outdated"
    ].join("\n")
  };

  const result = analyzeIssueIntake(issue);
  const classResult = AutobotIssueClassifier.analyzeIssueIntake(issue);

  assert.deepEqual(result.labels, ["documentation"]);
  assert.equal(result.releaseRelevant, false);
  assert.ok(result.evidenceItems.some((item) => item.ruleId === "issue-documentation-report"));
  assert.deepEqual(classResult.labels, result.labels);
});

test("prompt builder emits deterministic fallback summary", () => {
  const issue = {
    number: 14,
    title: "Bug: runtime failure on Windows",
    body: ""
  };

  const result = buildIssueSummaryArtifacts({ issue });
  const classResult = AutobotPromptBuilder.buildIssueSummaryArtifacts({ issue });

  assert.equal(result.ready, "true");
  assert.ok(result.fallbackSummary.includes("Issue #14"));
  assert.ok(result.fallbackSummary.includes("The issue body is empty"));
  assert.equal(classResult.fallbackSummary, result.fallbackSummary);
});

test("PR analyzer avoids feature-flag self-classification for autobot infrastructure", () => {
  const snapshot = {
    pullRequest: {
      number: 7,
      title: "Refine autobot release heuristics",
      body: "",
      headRef: "autobot/refactor"
    },
    totals: {
      filesChanged: 1,
      additions: 12,
      deletions: 2,
      totalChanges: 14
    },
    files: [
      {
        filename: ".github/scripts/autobot_project_manager.js",
        status: "modified",
        additions: 12,
        deletions: 2,
        patch: [
          "+ const rollout = \"feature-flag\";",
          "+ const note = \"release automation\";"
        ].join("\n"),
        rawPatchAvailable: true
      }
    ]
  };

  const result = analyzePullRequestSnapshotData(snapshot);
  const classResult = AutobotPullRequestAnalyzer.analyzePullRequestSnapshotData(snapshot);
  const deterministicLabels = JSON.parse(result.deterministic_labels_json);

  assert.ok(!deterministicLabels.includes("feature-flag"));
  assert.equal(classResult.deterministic_labels_json, result.deterministic_labels_json);
});

test("project manager resolves PR label deltas from the shared registry rules", () => {
  const result = resolvePrLabelDelta({
    action: "opened",
    previousBotLabels: ["bug", "workflow"],
    currentPrLabels: ["bug", "workflow", "documentation"],
    autobotLabelsRaw: JSON.stringify(["bug", "documentation"])
  });

  const classResult = AutobotProjectManager.resolvePrLabelDelta({
    action: "opened",
    previousBotLabels: ["bug", "workflow"],
    currentPrLabels: ["bug", "workflow", "documentation"],
    autobotLabelsRaw: JSON.stringify(["bug", "documentation"])
  });

  assert.deepEqual(result.labelsToAdd, []);
  assert.deepEqual(result.labelsToRemove, ["workflow"]);
  assert.deepEqual(result.nextAutobotLabels, ["bug", "documentation"]);
  assert.deepEqual(classResult, result);
});