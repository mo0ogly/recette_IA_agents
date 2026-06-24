/**
 * R16 contract gate for AgentAnalysisPanel: render against a REAL captured payload
 * (__fixtures__/agent-analysis.fixture.json, a live /probe/process-capture result)
 * and assert the discovery's report renders -- the agent, the coherent/divergent
 * verdict, the planned/said/done columns, and the logging recommendations.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AgentAnalysisPanel from "./AgentAnalysisPanel";
import type { AgentAnalysis } from "../../api/client";
import fixture from "./__fixtures__/agent-analysis.fixture.json";

const REAL: AgentAnalysis[] = fixture.agent_analysis as AgentAnalysis[];

describe("AgentAnalysisPanel", () => {
  it("renders nothing when there is no analysis", () => {
    const { container } = render(<AgentAnalysisPanel analysis={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the discovery report from a real captured payload", () => {
    render(<AgentAnalysisPanel analysis={REAL} />);
    expect(screen.getByTestId("agent-analysis-panel")).toBeInTheDocument();
    const a = REAL[0];
    expect(screen.getByTestId(`aa-agent-${a.agent_id}`)).toBeInTheDocument();
    // the three-way columns
    expect(screen.getByText("PLANNED (declared)")).toBeInTheDocument();
    expect(screen.getByText("SAID (decided)")).toBeInTheDocument();
    expect(screen.getByText("DONE (kernel saw)")).toBeInTheDocument();
    // the logging recommendations section + at least one rec
    expect(screen.getByText("What to log")).toBeInTheDocument();
    expect(screen.getByText(a.logging_recommendations[0].log)).toBeInTheDocument();
  });

  it("shows DIVERGENT + an ALERT recommendation for an exfiltrating agent", () => {
    // Cover the alert path (a real divergent capture is rare; the engine logic is
    // unit-tested in tests/test_agent_analysis.py -- here we assert the UI renders it).
    const divergent: AgentAnalysis[] = [
      {
        agent_id: "leak-bot",
        identified: true,
        seen_kinds: ["connect"],
        planned: { systems: ["gh-mock"], scope: ["read_repo"] },
        said: null,
        done: {
          dialed_servers: [],
          undeclared_egress: ["8.8.8.8:443"],
          undeclared_dns: [],
          process_spawned: false,
          sensitive_opens: [],
          credential_opens: [],
          doh_egress: [],
        },
        coherent: false,
        logging_recommendations: [
          {
            severity: "alert",
            log: "egress connect to UNDECLARED host 8.8.8.8:443",
            why: "possible exfiltration -- not in the server registry",
          },
        ],
        analysis: "DIVERGENT: undeclared egress 1.",
      },
    ];
    render(<AgentAnalysisPanel analysis={divergent} />);
    expect(screen.getByTestId("aa-verdict-leak-bot")).toHaveTextContent("DIVERGENT");
    expect(screen.getByText("ALERT")).toBeInTheDocument();
    expect(
      screen.getByText("egress connect to UNDECLARED host 8.8.8.8:443"),
    ).toBeInTheDocument();
  });

  it("renders credential-leave and DoH-tunnel signals in the DONE column", () => {
    const hardened: AgentAnalysis[] = [
      {
        agent_id: "exfil-bot",
        identified: true,
        seen_kinds: ["connect", "open"],
        planned: { systems: ["gh-mock"], scope: ["read_repo"] },
        said: { actions: ["read_repo"] },
        done: {
          dialed_servers: ["gh-mock"],
          undeclared_egress: ["8.8.8.8:443"],
          undeclared_dns: [],
          process_spawned: false,
          sensitive_opens: [],
          credential_opens: ["/home/bot/.aws/credentials"],
          doh_egress: ["8.8.8.8"],
        },
        coherent: false,
        logging_recommendations: [
          {
            severity: "alert",
            log: "credential/secret file access /home/bot/.aws/credentials",
            why: "secret-material read (ATLAS AML.T0055) -- exfil-prep, never routine I/O",
          },
          {
            severity: "alert",
            log: "egress to public DNS resolver 8.8.8.8:443",
            why: "DNS-over-HTTPS covert channel -- tunneling exfil past a port-53 allow-list",
          },
        ],
        analysis: "DIVERGENT: 1 credential leave(s), 1 DoH resolver(s).",
      },
    ];
    render(<AgentAnalysisPanel analysis={hardened} />);
    expect(screen.getByText("CREDENTIAL /home/bot/.aws/credentials")).toBeInTheDocument();
    expect(screen.getByText("DoH 8.8.8.8:443")).toBeInTheDocument();
    expect(
      screen.getByText("credential/secret file access /home/bot/.aws/credentials"),
    ).toBeInTheDocument();
  });
});
