import {
  Alert,
  Button,
  FormField,
  MultilineInput,
  Rows,
  Text,
  Title,
} from "@canva/app-ui-kit";
import {
  getDesignMetadata,
  openDesign,
  requestExport,
  type ExportResponse,
  type DesignEditing,
} from "@canva/design";
import { useState } from "react";
import * as styles from "styles/components.css";

type PlaceholderBinding = {
  left: number;
  top: number;
  width: number;
  font_size: number;
};

type RuntimeJob = {
  version: string;
  request_type: string;
  template: {
    template_name: string;
    required_keyword?: string;
  };
  payload: {
    title: string;
    audience?: string;
    tone?: string;
    content?: string;
    executive_summary: string[];
    strategic_priorities: string[];
    risk_matrix: Array<{
      risk: string;
      impact: string;
      mitigation: string;
      owner: string;
    }>;
    citations: Array<{
      id: string;
      source: string;
      note: string;
    }>;
    annexes?: Array<{
      title: string;
      summary: string;
      items: string[];
    }>;
  };
  placeholder_bindings: Record<string, PlaceholderBinding>;
};

const REQUIRED_SECTIONS = [
  "title",
  "executive_summary",
  "strategic_priorities",
  "risk_matrix",
  "citations",
];
const REQUIRED_CITATION_IDS = ["SR-1", "SR-2"];

function assertAbsolutePage(page: DesignEditing.Page): asserts page is DesignEditing.AbsolutePage {
  if (page.type !== "absolute") {
    throw new Error("Current page type is not supported for C-suite template hydration");
  }
}

function sectionText(job: RuntimeJob, section: string): string {
  const payload = job.payload;

  const citationsById = new Map<string, { id: string; source: string; note: string }>();
  payload.citations.forEach((item) => {
    citationsById.set(item.id.trim().toUpperCase(), item);
  });
  REQUIRED_CITATION_IDS.forEach((citationId) => {
    if (citationsById.has(citationId)) {
      return;
    }
    citationsById.set(citationId, {
      id: citationId,
      source: "Compliance citation placeholder",
      note: "Replace with validated legal source.",
    });
  });

  switch (section) {
    case "title":
      return `PRIVILEGED & CONFIDENTIAL\n${payload.title}`;
    case "executive_summary":
      return ["Executive Summary", ...payload.executive_summary.map((line) => `- ${line}`)].join("\n");
    case "strategic_priorities":
      return [
        "Strategic Priorities",
        ...payload.strategic_priorities.map((line, index) => `${index + 1}. ${line}`),
      ].join("\n");
    case "risk_matrix":
      return [
        "Risk Matrix",
        ...payload.risk_matrix.map(
          (row, index) =>
            `${index + 1}. Risk: ${row.risk}; Impact: ${row.impact}; Mitigation: ${row.mitigation}; Owner: ${row.owner}`,
        ),
      ].join("\n");
    case "citations":
      return [
        "Citations",
        ...Array.from(citationsById.values()).map((item) => `[${item.id}] ${item.source} :: ${item.note}`),
      ].join("\n");
    case "annexes":
      return [
        "Annexes",
        ...(payload.annexes || []).map(
          (annex, index) =>
            `${index + 1}. ${annex.title}: ${annex.summary}${annex.items.length ? ` (${annex.items.join("; ")})` : ""}`,
        ),
      ].join("\n");
    default:
      return "";
  }
}

async function verifyTemplateKeyword(job: RuntimeJob): Promise<void> {
  const requiredKeyword = (job.template.required_keyword || "C-SUITE-EXEC").toLowerCase();
  const declaredTemplateName = (job.template.template_name || "").toLowerCase();

  if (!declaredTemplateName.includes(requiredKeyword)) {
    throw new Error(
      `Runtime job template '${job.template.template_name}' does not satisfy required template keyword '${job.template.required_keyword || "C-SUITE-EXEC"}'.`,
    );
  }

  const metadata = await getDesignMetadata();
  const designTitle = (metadata.title || "").toLowerCase();
  if (designTitle && !designTitle.includes(requiredKeyword)) {
    throw new Error(
      `Active Canva design title '${metadata.title}' does not match required keyword '${job.template.required_keyword || "C-SUITE-EXEC"}'. Open the approved C-suite template before export.`,
    );
  }

  // Some Canva editors may not expose a user-set title; proceed when title is unavailable.
}

async function applyJobToDesign(job: RuntimeJob): Promise<void> {
  REQUIRED_SECTIONS.forEach((key) => {
    if (!job.placeholder_bindings[key]) {
      throw new Error(`Missing required placeholder binding: ${key}`);
    }
  });

  await openDesign({ type: "current_page" }, async (session) => {
    assertAbsolutePage(session.page);

    const { elementStateBuilder } = session.helpers;

    const sections = [...REQUIRED_SECTIONS, "annexes"];
    sections.forEach((section) => {
      const binding = job.placeholder_bindings[section];
      if (!binding) {
        return;
      }

      const body = sectionText(job, section);
      if (!body.trim()) {
        return;
      }

      const richText = elementStateBuilder.createRichtextRange();
      richText.appendText(body);
      richText.formatParagraph(
        { index: 0, length: body.length },
        {
          fontSize: binding.font_size,
        },
      );

      session.page.elements.insertBefore(
        undefined,
        elementStateBuilder.createTextElement({
          text: { regions: richText.readTextRegions() },
          left: binding.left,
          top: binding.top,
          width: binding.width,
        }),
      );
    });

    await session.sync();
  });
}

export const App = () => {
  const [jobText, setJobText] = useState("");
  const [status, setStatus] = useState<"idle" | "running" | "success" | "error">("idle");
  const [error, setError] = useState<string>("");
  const [exportResponse, setExportResponse] = useState<ExportResponse | undefined>(undefined);

  const onRun = async () => {
    if (status === "running") {
      return;
    }

    try {
      setStatus("running");
      setError("");

      const parsed = JSON.parse(jobText) as RuntimeJob;

      await verifyTemplateKeyword(parsed);
      await applyJobToDesign(parsed);

      const response = await requestExport({
        acceptedFileTypes: ["pdf_standard"],
      });

      setExportResponse(response);
      setStatus("success");
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Unknown runtime error");
    }
  };

  return (
    <div className={styles.scrollContainer}>
      <Rows spacing="2u">
        <Title size="small">C-Suite Executive PDF Hydration</Title>
        <Text>
          Paste the runtime job JSON produced by Codex, hydrate the approved template, and export PDF using one-click
          Canva export.
        </Text>

        <FormField
          label="Runtime job JSON"
          value={jobText}
          control={(props) => <MultilineInput {...props} maxRows={16} autoGrow onChange={setJobText} />}
        />

        <Button variant="primary" onClick={onRun} loading={status === "running"} stretch>
          Hydrate Template and Export PDF
        </Button>

        {status === "success" && (
          <Alert tone="positive">Template hydration applied. Export request issued successfully.</Alert>
        )}

        {status === "error" && <Alert tone="critical">{error}</Alert>}

        {exportResponse && (
          <FormField
            label="Export response"
            value={JSON.stringify(exportResponse, null, 2)}
            control={(props) => <MultilineInput {...props} maxRows={10} autoGrow readOnly />}
          />
        )}
      </Rows>
    </div>
  );
};
