// Deep Signal - Supply Chain Graph Visualization
// Uses vis.js for interactive network graph rendering

const API_BASE = window.DS_API_BASE || "";

// Global state
let currentGraphData = null;
let network = null;
let allNodes = null;
let allEdges = null;
let activeFilters = {
  nodeTypes: new Set(),
  minConfidence: 0,
  searchQuery: "",
  cveSeverity: "all"
};

// Node type configuration
const NODE_TYPES = {
  repo: {
    label: "Repository",
    color: "#2563eb",
    shape: "box",
    icon: "📦"
  },
  release: {
    label: "Release",
    color: "#16a34a",
    shape: "diamond",
    icon: "🏷️"
  },
  maintainer: {
    label: "Maintainer",
    color: "#9333ea",
    shape: "dot",
    icon: "👤"
  },
  cve: {
    label: "CVE",
    color: "#dc2626",
    shape: "triangle",
    icon: "⚠️"
  },
  registry: {
    label: "Registry",
    color: "#ea580c",
    shape: "hexagon",
    icon: "📚"
  },
  risk_factor: {
    label: "Risk Factor",
    color: "#ca8a04",
    shape: "dot",
    icon: "⚡",
    size: 18
  }
};

// Utility functions
function el(id) {
  return document.getElementById(id);
}

function showError(msg) {
  const box = el("err");
  box.style.display = msg ? "block" : "none";
  box.textContent = msg || "";
}

function setLoading(isLoading) {
  const btn = el("loadBtn");
  btn.textContent = isLoading ? "Loading…" : "Load Graph";
  btn.disabled = !!isLoading;
  el("refreshBtn").disabled = !!isLoading;
}

function getConfidenceBadge(confidence) {
  if (confidence == null) return "";
  
  const conf = Number(confidence);
  let className = "confidence-low";
  let label = "Low";
  
  if (conf >= 0.9) {
    className = "confidence-high";
    label = "High";
  } else if (conf >= 0.8) {
    className = "confidence-medium";
    label = "Medium";
  }
  
  return `<span class="confidence-badge ${className}">${label} (${conf.toFixed(2)})</span>`;
}

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  try {
    const date = new Date(timestamp);
    return date.toLocaleString();
  } catch (e) {
    return timestamp;
  }
}

// Initialize node type filters
function initializeFilters() {
  const container = el("nodeTypeFilters");
  container.innerHTML = "";
  
  // Initialize all node types as enabled
  Object.keys(NODE_TYPES).forEach(type => {
    activeFilters.nodeTypes.add(type);
  });
  
  Object.entries(NODE_TYPES).forEach(([type, config]) => {
    const label = document.createElement("label");
    label.className = "filter-check";
    label.innerHTML = `
      <input type="checkbox" value="${type}" checked />
      <span class="node-badge" style="background-color: ${config.color};"></span>
      <span>${config.icon} ${config.label}</span>
    `;
    
    const checkbox = label.querySelector("input");
    checkbox.addEventListener("change", (e) => {
      if (e.target.checked) {
        activeFilters.nodeTypes.add(type);
      } else {
        activeFilters.nodeTypes.delete(type);
      }
      applyFilters();
    });
    
    container.appendChild(label);
  });
}

// Confidence slider
el("confidenceSlider").addEventListener("input", (e) => {
  const value = parseInt(e.target.value) / 100;
  el("confidenceValue").textContent = value.toFixed(2);
  activeFilters.minConfidence = value;
  applyFilters();
});

// Search input
el("searchInput").addEventListener("input", (e) => {
  activeFilters.searchQuery = e.target.value.toLowerCase().trim();
  applyFilters();
});

// CVE severity filter
el("cveSeverityFilter").addEventListener("change", (e) => {
  activeFilters.cveSeverity = e.target.value;
  applyFilters();
});

// Apply filters to graph
function applyFilters() {
  if (!network || !allNodes || !allEdges) return;
  
  // Filter nodes
  const filteredNodes = allNodes.get().filter(node => {
    // Type filter
    if (!activeFilters.nodeTypes.has(node.nodeType)) {
      return false;
    }
    
    // Confidence filter
    const confidence = node.confidence || 1.0;
    if (confidence < activeFilters.minConfidence) {
      return false;
    }
    
    // CVE severity filter
    if (node.nodeType === "cve" && activeFilters.cveSeverity !== "all") {
      // Parse severity from CVSS vector string
      // Example: "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
      // C=Confidentiality, I=Integrity, A=Availability
      // H=High, L=Low, N=None
      
      let severityLevel = "LOW"; // default
      const severityStr = node.metadata?.severity || "";
      
      // Count high-impact components (C:H, I:H, A:H)
      const highCount = (severityStr.match(/[CIA]:H/g) || []).length;
      const mediumCount = (severityStr.match(/[CIA]:M/g) || []).length;
      
      // Heuristic: 3 highs = CRITICAL, 1-2 highs = HIGH, mediums = MEDIUM
      if (highCount >= 3) {
        severityLevel = "CRITICAL";
      } else if (highCount >= 1) {
        severityLevel = "HIGH";
      } else if (mediumCount >= 1) {
        severityLevel = "MEDIUM";
      }
      
      // Apply filter
      if (activeFilters.cveSeverity === "critical" && severityLevel !== "CRITICAL") {
        return false;
      }
      
      if (activeFilters.cveSeverity === "high-critical" && 
          severityLevel !== "CRITICAL" && severityLevel !== "HIGH") {
        return false;
      }
    }
    
    // Search filter
    if (activeFilters.searchQuery) {
      const label = (node.label || "").toLowerCase();
      const id = (node.id || "").toLowerCase();
      if (!label.includes(activeFilters.searchQuery) && !id.includes(activeFilters.searchQuery)) {
        return false;
      }
    }
    
    return true;
  });
  
  const visibleNodeIds = new Set(filteredNodes.map(n => n.id));
  
  // Filter edges (only show edges where both nodes are visible)
  const filteredEdges = allEdges.get().filter(edge => {
    return visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to);
  });
  
  // Update network
  network.setData({
    nodes: new vis.DataSet(filteredNodes),
    edges: new vis.DataSet(filteredEdges)
  });
  
  // Update stats to show filtered counts
  el("nodeCount").textContent = filteredNodes.length;
  el("edgeCount").textContent = filteredEdges.length;
}

// Convert graph data to vis.js format
function convertToVisFormat(graphData) {
  const nodes = graphData.graph.nodes.map(node => {
    const nodeType = node.type;
    const config = NODE_TYPES[nodeType] || NODE_TYPES.repo;
    
    // Get confidence from provenance
    const confidence = node.provenance?.data_confidence || 
                      node.provenance?.confidence || 
                      1.0;
    
    // Determine border style based on confidence
    let borderDashes = false;
    let opacity = 1.0;
    
    if (confidence < 0.8) {
      borderDashes = [5, 5];
      opacity = 0.8;
    } else if (confidence < 0.9) {
      opacity = 0.9;
    }
    
    // Build tooltip
    const tooltip = buildNodeTooltip(node);
    
    // Risk factor nodes: dot shape with truncated external label
    const isRiskFactor = nodeType === "risk_factor";
    const displayLabel = isRiskFactor && node.label.length > 22
      ? node.label.slice(0, 20) + "…"
      : node.label;

    const visNode = {
      id: node.id,
      label: displayLabel,
      shape: config.shape,
      color: {
        background: config.color,
        border: adjustColorBrightness(config.color, -20),
        highlight: {
          background: adjustColorBrightness(config.color, 20),
          border: adjustColorBrightness(config.color, -10)
        }
      },
      font: {
        color: "#ffffff",
        size: isRiskFactor ? 10 : 14,
        face: "ui-sans-serif, system-ui",
        vadjust: isRiskFactor ? -24 : 0
      },
      borderWidth: 2,
      borderWidthSelected: 3,
      shapeProperties: {
        borderDashes: borderDashes
      },
      opacity: opacity,
      title: tooltip,
      nodeType: nodeType,
      confidence: confidence,
      metadata: node.metadata,
      provenance: node.provenance
    };

    // Dot-shaped nodes need explicit size
    if (config.size) {
      visNode.size = config.size;
    }

    return visNode;
  });
  
  const edges = graphData.graph.edges.map(edge => {
    // Get confidence from provenance
    const confidence = edge.provenance?.confidence || 
                      edge.provenance?.match_confidence || 
                      1.0;
    
    // Determine edge style based on relationship and confidence
    let color = "#6b7280";
    let width = 2;
    let dashes = false;
    
    // High-risk relationships (CVE)
    if (edge.relationship_type === "has_cve") {
      color = "#dc2626";
      width = 3;
    }
    
    // Low confidence edges
    if (confidence < 0.8) {
      dashes = [5, 5];
    }
    
    // Edge opacity based on confidence
    const opacity = 0.5 + (0.5 * confidence);
    
    // Build tooltip for edge
    const edgeLabel = edge.relationship_type.replace(/_/g, " ");
    const edgeTooltip = `${edgeLabel}\nConfidence: ${(confidence * 100).toFixed(0)}%`;
    
    return {
      from: edge.source,
      to: edge.target,
      arrows: {
        to: {
          enabled: true,
          scaleFactor: 0.5
        }
      },
      color: {
        color: color,
        opacity: opacity,
        highlight: adjustColorBrightness(color, 30)
      },
      width: width,
      dashes: dashes,
      smooth: {
        type: "cubicBezier",
        roundness: 0.5
      },
      title: edgeTooltip,
      // No label by default - cleaner view
      relationshipType: edge.relationship_type,
      metadata: edge.metadata,
      provenance: edge.provenance
    };
  });
  
  return { nodes, edges };
}

// Build tooltip for node hover
function buildNodeTooltip(node) {
  const lines = [
    `${node.label}`,
    `Type: ${node.type}`
  ];
  
  // Add key metadata
  if (node.metadata) {
    const meta = node.metadata;
    
    if (meta.tag_name) lines.push(`Tag: ${meta.tag_name}`);
    if (meta.username) lines.push(`User: ${meta.username}`);
    if (meta.severity) lines.push(`Severity: ${meta.severity}`);
    if (meta.registry_type) lines.push(`Registry: ${meta.registry_type}`);
    if (meta.key) lines.push(`Metric: ${meta.key}`);
  }
  
  // Add confidence
  if (node.provenance) {
    const conf = node.provenance.data_confidence || node.provenance.confidence;
    if (conf != null) {
      lines.push(`Confidence: ${(conf * 100).toFixed(0)}%`);
    }
  }
  
  return lines.join("\n");
}

// Adjust color brightness
function adjustColorBrightness(color, percent) {
  const num = parseInt(color.replace("#", ""), 16);
  const amt = Math.round(2.55 * percent);
  const R = (num >> 16) + amt;
  const G = (num >> 8 & 0x00FF) + amt;
  const B = (num & 0x0000FF) + amt;
  return "#" + (0x1000000 + (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 +
    (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 +
    (B < 255 ? B < 1 ? 0 : B : 255))
    .toString(16).slice(1);
}

// Render graph using vis.js
function renderGraph(graphData) {
  console.log("renderGraph called with data:", graphData);
  currentGraphData = graphData;
  
  // Convert to vis.js format
  const { nodes, edges } = convertToVisFormat(graphData);
  console.log("Converted to vis format:", { nodeCount: nodes.length, edgeCount: edges.length });
  
  // Store all nodes and edges for filtering
  allNodes = new vis.DataSet(nodes);
  allEdges = new vis.DataSet(edges);
  
  // Get container
  const container = el("graph-container");
  console.log("Container element:", container, "Dimensions:", container.offsetWidth, "x", container.offsetHeight);
  container.innerHTML = "";
  
  // Network options
  const options = {
    layout: {
      hierarchical: {
        enabled: true,
        direction: "UD",
        sortMethod: "directed",
        nodeSpacing: 200,
        levelSeparation: 250,
        treeSpacing: 250,
        blockShifting: true,
        edgeMinimization: true,
        parentCentralization: true
      }
    },
    physics: {
      enabled: false
    },
    interaction: {
      hover: true,
      zoomView: true,
      dragView: true,
      navigationButtons: true,
      keyboard: true,
      tooltipDelay: 100
    },
    nodes: {
      size: 25,
      font: {
        size: 14,
        color: "#ffffff"
      }
    },
    edges: {
      smooth: {
        type: "cubicBezier",
        roundness: 0.5
      }
    }
  };
  
  // Create network
  console.log("Creating vis.Network...");
  network = new vis.Network(container, {
    nodes: allNodes,
    edges: allEdges
  }, options);
  console.log("Network created:", network);
  
  // Fit the network to show all nodes
  setTimeout(() => {
    network.fit({
      animation: {
        duration: 500,
        easingFunction: "easeInOutQuad"
      }
    });
    console.log("Network fitted to viewport");
  }, 100);
  
  // Event handlers
  network.on("click", (params) => {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      showNodeDetails(nodeId);
    } else {
      clearNodeDetails();
    }
  });
  
  network.on("hoverNode", () => {
    container.style.cursor = "pointer";
  });
  
  network.on("blurNode", () => {
    container.style.cursor = "default";
  });
  
  // Update stats
  updateGraphStats(graphData);
  
  // Show export buttons
  el("exportButtons").style.display = "flex";
  el("provenanceToggle").style.display = "flex";
}

// Update graph statistics
function updateGraphStats(graphData) {
  el("nodeCount").textContent = graphData.graph.nodes.length;
  el("edgeCount").textContent = graphData.graph.edges.length;
  el("graphStats").style.display = "flex";
}

// Show node details in side panel
function showNodeDetails(nodeId) {
  const node = allNodes.get(nodeId);
  if (!node) return;
  
  const showProvenance = el("showProvenance").checked;
  
  let html = `
    <div class="detail-section">
      <h4>Basic Info</h4>
      <div class="detail-item">
        <div class="label">ID</div>
        <div class="value">${node.id}</div>
      </div>
      <div class="detail-item">
        <div class="label">Type</div>
        <div class="value">${NODE_TYPES[node.nodeType]?.icon || ""} ${NODE_TYPES[node.nodeType]?.label || node.nodeType}</div>
      </div>
      <div class="detail-item">
        <div class="label">Label</div>
        <div class="value">${node.label}</div>
      </div>
    </div>
  `;
  
  // Metadata section
  if (node.metadata && Object.keys(node.metadata).length > 0) {
    html += `<div class="detail-section"><h4>Metadata</h4>`;
    
    Object.entries(node.metadata).forEach(([key, value]) => {
      if (value != null && value !== "") {
        html += `
          <div class="detail-item">
            <div class="label">${key.replace(/_/g, " ")}</div>
            <div class="value">${formatValue(value)}</div>
          </div>
        `;
      }
    });
    
    html += `</div>`;
  }
  
  // Provenance section (if enabled)
  if (showProvenance && node.provenance) {
    html += `<div class="detail-section"><h4>Provenance</h4>`;
    
    if (node.provenance.source) {
      html += `
        <div class="detail-item">
          <div class="label">Source</div>
          <div class="value">${node.provenance.source}</div>
        </div>
      `;
    }
    
    if (node.provenance.fetched_at) {
      html += `
        <div class="detail-item">
          <div class="label">Fetched At</div>
          <div class="value">${formatTimestamp(node.provenance.fetched_at)}</div>
        </div>
      `;
    }
    
    const confidence = node.provenance.data_confidence || node.provenance.confidence;
    if (confidence != null) {
      html += `
        <div class="detail-item">
          <div class="label">Confidence</div>
          <div class="value">${getConfidenceBadge(confidence)}</div>
        </div>
      `;
    }
    
    if (node.provenance.match_confidence != null) {
      html += `
        <div class="detail-item">
          <div class="label">Match Confidence</div>
          <div class="value">${getConfidenceBadge(node.provenance.match_confidence)}</div>
        </div>
      `;
    }
    
    html += `</div>`;
  }
  
  el("nodeDetails").innerHTML = html;

  // Reorder sidebar: move Selected Node to top (after insight panel), demote Graph Summary
  const sidebar = document.getElementById("sidebarContainer");
  const selectedPanel = document.getElementById("selectedNodePanel");
  const summaryPanel = document.getElementById("graphSummaryPanel");
  const insightPanel = document.getElementById("insightPanel");
  if (sidebar && selectedPanel && summaryPanel) {
    // Insert Selected Node right after Insight (or first if insight hidden)
    const anchor = insightPanel && insightPanel.style.display !== "none"
      ? insightPanel.nextSibling
      : sidebar.firstChild;
    sidebar.insertBefore(selectedPanel, anchor);
    // Ensure Graph Summary comes after Selected Node
    sidebar.insertBefore(summaryPanel, selectedPanel.nextSibling);
    // Add state class for CSS demotion
    sidebar.classList.add("sidebar-node-active");
  }
}

// Clear node details
function clearNodeDetails() {
  el("nodeDetails").innerHTML = `
    <div style="font-size:13px;color:var(--text-tertiary);line-height:1.5;">
      Select a node to inspect its role, relationships, and risk context.
    </div>
  `;

  // Restore sidebar order: Insight → Graph Summary → Selected Node
  const sidebar = document.getElementById("sidebarContainer");
  const selectedPanel = document.getElementById("selectedNodePanel");
  const summaryPanel = document.getElementById("graphSummaryPanel");
  if (sidebar && selectedPanel && summaryPanel) {
    // Move Graph Summary before Selected Node (original order)
    sidebar.insertBefore(summaryPanel, selectedPanel);
    sidebar.classList.remove("sidebar-node-active");
  }
}

// Format value for display
function formatValue(value) {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value === "number") {
    if (value < 1 && value > 0) {
      return value.toFixed(4);
    }
    return value.toLocaleString();
  }
  if (typeof value === "string" && value.match(/^\d{4}-\d{2}-\d{2}T/)) {
    return formatTimestamp(value);
  }
  return String(value);
}

// Provenance toggle
el("showProvenance").addEventListener("change", () => {
  // Re-render current node details if any
  if (network) {
    const selected = network.getSelectedNodes();
    if (selected.length > 0) {
      showNodeDetails(selected[0]);
    }
  }
});

// Export functions
el("exportJson").addEventListener("click", () => {
  if (!currentGraphData) return;
  
  const dataStr = JSON.stringify(currentGraphData, null, 2);
  const dataBlob = new Blob([dataStr], { type: "application/json" });
  const url = URL.createObjectURL(dataBlob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${currentGraphData.repo.replace("/", "_")}_graph.json`;
  link.click();
  URL.revokeObjectURL(url);
});

el("exportPng").addEventListener("click", () => {
  if (!network) return;
  
  // Use vis.js canvas to export
  const canvas = document.querySelector("#graph-container canvas");
  if (canvas) {
    canvas.toBlob((blob) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${currentGraphData.repo.replace("/", "_")}_graph.png`;
      link.click();
      URL.revokeObjectURL(url);
    });
  }
});

// Load graph from API
async function loadGraph(refresh = false) {
  console.log("loadGraph called, refresh:", refresh);
  showError("");
  setLoading(true);
  clearNodeDetails();
  
  const repo = el("repoInput").value.trim() || "numpy/numpy";
  console.log("Loading graph for repo:", repo);
  
  const url = new URL(API_BASE + "/api/graph", window.location.origin);
  url.searchParams.set("repo", repo);
  url.searchParams.set("refresh", String(refresh));
  url.searchParams.set("max_risk_factors", "10");  // Show more risk factors by default
  
  try {
    console.log("Fetching from:", url.toString());
    const res = await fetch(url.toString());
    const text = await res.text();
    console.log("Response status:", res.status, "Response length:", text.length);
    
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}\n${text}`);
    }
    
    const graphData = JSON.parse(text);
    console.log("Parsed graph data:", graphData);
    
    // Check if graph is empty
    if (!graphData.graph.nodes || graphData.graph.nodes.length === 0) {
      showError("Graph is empty. The repository may not have enough data.");
      return;
    }
    
    console.log("About to call renderGraph with", graphData.graph.nodes.length, "nodes");
    renderGraph(graphData);
    console.log("renderGraph completed");

    // Fire-and-forget insight panel fetch (Task 5.3)
    if (typeof fetchAndRenderInsight === "function") {
      var repoParts = repo.replace(/^https?:\/\/github\.com\//, "").split("/");
      if (repoParts.length >= 2) {
        fetchAndRenderInsight(repoParts[0], repoParts[1]);
      }
    }
    
  } catch (e) {
    console.error("Error loading graph:", e);
    showError(String(e));
    
    // Show empty state
    const container = el("graph-container");
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">❌</div>
        <div>Failed to load graph</div>
      </div>
    `;
  } finally {
    setLoading(false);
  }
}

// Event listeners
el("loadBtn").addEventListener("click", () => loadGraph(false));
el("refreshBtn").addEventListener("click", () => loadGraph(true));
el("repoInput").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") loadGraph(false);
});

// Initialize
initializeFilters();
el("repoInput").value = "numpy/numpy";
