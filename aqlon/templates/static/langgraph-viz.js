/**
 * LangGraph Visualization Library for AQLON
 * This script renders a visual representation of the LangGraph workflow
 */

class LangGraphVisualizer {
  constructor(containerId, graphData, options = {}) {
    this.container = document.getElementById(containerId);
    if (!this.container) {
      throw new Error(`Container element with ID '${containerId}' not found`);
    }

    this.graphData = graphData;
    this.options = Object.assign(
      {
        nodeRadius: 40,
        nodeSpacing: 180,
        levelHeight: 150,
        animationDuration: 500,
        colors: {
          node: {
            default: "#3498db",
            active: "#2ecc71",
            completed: "#95a5a6",
            current: "#e74c3c",
          },
          edge: {
            default: "#bdc3c7",
            active: "#3498db",
            conditional: "#9b59b6",
          },
        },
      },
      options
    );

    this.svg = null;
    this.currentState = null;
    this.nodeElements = {};
    this.edgeElements = {};

    this.init();
  }

  init() {
    // Clear any existing content
    this.container.innerHTML = "";

    // Create SVG container
    this.svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    this.svg.setAttribute("width", "100%");
    this.svg.setAttribute("height", "100%");
    this.svg.setAttribute("viewBox", "0 0 1000 500");
    this.container.appendChild(this.svg);

    // Add definitions for markers (arrowheads)
    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");

    // Default arrow
    const defaultArrow = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "marker"
    );
    defaultArrow.setAttribute("id", "arrow-default");
    defaultArrow.setAttribute("viewBox", "0 0 10 10");
    defaultArrow.setAttribute("refX", "9");
    defaultArrow.setAttribute("refY", "5");
    defaultArrow.setAttribute("markerWidth", "6");
    defaultArrow.setAttribute("markerHeight", "6");
    defaultArrow.setAttribute("orient", "auto");

    const defaultPath = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "path"
    );
    defaultPath.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
    defaultPath.setAttribute("fill", this.options.colors.edge.default);
    defaultArrow.appendChild(defaultPath);
    defs.appendChild(defaultArrow);

    // Active arrow
    const activeArrow = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "marker"
    );
    activeArrow.setAttribute("id", "arrow-active");
    activeArrow.setAttribute("viewBox", "0 0 10 10");
    activeArrow.setAttribute("refX", "9");
    activeArrow.setAttribute("refY", "5");
    activeArrow.setAttribute("markerWidth", "6");
    activeArrow.setAttribute("markerHeight", "6");
    activeArrow.setAttribute("orient", "auto");

    const activePath = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "path"
    );
    activePath.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
    activePath.setAttribute("fill", this.options.colors.edge.active);
    activeArrow.appendChild(activePath);
    defs.appendChild(activeArrow);

    // Conditional arrow
    const conditionalArrow = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "marker"
    );
    conditionalArrow.setAttribute("id", "arrow-conditional");
    conditionalArrow.setAttribute("viewBox", "0 0 10 10");
    conditionalArrow.setAttribute("refX", "9");
    conditionalArrow.setAttribute("refY", "5");
    conditionalArrow.setAttribute("markerWidth", "6");
    conditionalArrow.setAttribute("markerHeight", "6");
    conditionalArrow.setAttribute("orient", "auto");

    const conditionalPath = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "path"
    );
    conditionalPath.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
    conditionalPath.setAttribute("fill", this.options.colors.edge.conditional);
    conditionalArrow.appendChild(conditionalPath);
    defs.appendChild(conditionalArrow);

    this.svg.appendChild(defs);

    // Initial render if we have data
    if (this.graphData) {
      this.renderGraph(this.graphData);
    }
  }

  renderGraph(graphData) {
    this.graphData = graphData;

    if (!graphData || !graphData.nodes) {
      this.renderEmptyState();
      return;
    }

    // Calculate node positions
    this.calculateNodePositions();

    // Render edges first (so they appear behind nodes)
    this.renderEdges();

    // Render nodes
    this.renderNodes();
  }

  calculateNodePositions() {
    const { nodeSpacing, levelHeight } = this.options;
    const nodes = this.graphData.nodes;

    // Simple layout for nodes organized by levels
    let levels = {};

    // First, identify entry point and place it in level 0
    const entryNode = nodes.find((n) => n.isEntry) || nodes[0];
    levels[0] = [entryNode.id];

    let currentLevel = 0;
    let placedNodes = new Set([entryNode.id]);

    // Keep adding levels until all nodes are placed
    while (placedNodes.size < nodes.length) {
      levels[currentLevel + 1] = [];

      // For each node in the current level
      levels[currentLevel].forEach((nodeId) => {
        const outgoingEdges = this.graphData.edges.filter(
          (e) => e.source === nodeId
        );

        // Add destination nodes to next level if not already placed
        outgoingEdges.forEach((edge) => {
          if (!placedNodes.has(edge.target)) {
            levels[currentLevel + 1].push(edge.target);
            placedNodes.add(edge.target);
          }
        });
      });

      // If no new nodes were added but we still have unplaced nodes
      if (levels[currentLevel + 1].length === 0) {
        const remainingNodes = nodes
          .filter((n) => !placedNodes.has(n.id))
          .map((n) => n.id);
        levels[currentLevel + 1] = remainingNodes;
        remainingNodes.forEach((id) => placedNodes.add(id));
      }

      currentLevel++;
    }

    // Calculate x,y coordinates for each node
    Object.entries(levels).forEach(([level, nodeIds]) => {
      const levelNum = parseInt(level);
      const y = 100 + levelNum * levelHeight;

      nodeIds.forEach((nodeId, index) => {
        const node = nodes.find((n) => n.id === nodeId);
        const x =
          100 + index * nodeSpacing + (nodeSpacing * (6 - nodeIds.length)) / 2;

        node.x = x;
        node.y = y;
      });
    });
  }

  renderNodes() {
    const { nodeRadius } = this.options;

    this.graphData.nodes.forEach((node) => {
      // Create group for node
      const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
      group.setAttribute("class", "node");
      group.setAttribute("data-id", node.id);

      // Create circle
      const circle = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "circle"
      );
      circle.setAttribute("cx", node.x);
      circle.setAttribute("cy", node.y);
      circle.setAttribute("r", nodeRadius);
      circle.setAttribute("fill", this.getNodeColor(node));
      circle.setAttribute("stroke", "#2c3e50");
      circle.setAttribute("stroke-width", "2");

      // Create text label
      const text = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "text"
      );
      text.setAttribute("x", node.x);
      text.setAttribute("y", node.y + nodeRadius + 20);
      text.setAttribute("text-anchor", "middle");
      text.setAttribute("fill", "#2c3e50");
      text.setAttribute("font-size", "14px");
      text.textContent = node.name;

      // Add hover effect
      group.addEventListener("mouseenter", () => this.onNodeHover(node));
      group.addEventListener("mouseleave", () => this.onNodeLeave(node));

      // Append elements to group and group to SVG
      group.appendChild(circle);
      group.appendChild(text);
      this.svg.appendChild(group);

      // Store reference to node elements
      this.nodeElements[node.id] = group;
    });
  }

  renderEdges() {
    this.graphData.edges.forEach((edge) => {
      const sourceNode = this.graphData.nodes.find((n) => n.id === edge.source);
      const targetNode = this.graphData.nodes.find((n) => n.id === edge.target);

      if (!sourceNode || !targetNode) return;

      // Create path for edge
      const path = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "path"
      );

      // Determine if it's a direct or curved path
      const isDirectPath =
        Math.abs(sourceNode.y - targetNode.y) <= this.options.levelHeight;
      let pathData;

      if (isDirectPath) {
        // Direct path
        pathData = `M${sourceNode.x},${sourceNode.y} L${targetNode.x},${targetNode.y}`;
      } else {
        // Curved path
        const controlPointY = (sourceNode.y + targetNode.y) / 2;
        pathData = `M${sourceNode.x},${sourceNode.y} C${sourceNode.x},${controlPointY} ${targetNode.x},${controlPointY} ${targetNode.x},${targetNode.y}`;
      }

      path.setAttribute("d", pathData);
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", this.getEdgeColor(edge));
      path.setAttribute("stroke-width", "2");

      // Add arrow marker
      if (edge.type === "conditional") {
        path.setAttribute("marker-end", "url(#arrow-conditional)");
        path.setAttribute("stroke-dasharray", "5,5");
      } else if (edge.active) {
        path.setAttribute("marker-end", "url(#arrow-active)");
      } else {
        path.setAttribute("marker-end", "url(#arrow-default)");
      }

      // Add label for conditional edges
      if (edge.type === "conditional" && edge.label) {
        // Calculate position for label
        const midX = (sourceNode.x + targetNode.x) / 2;
        const midY = (sourceNode.y + targetNode.y) / 2;

        const label = document.createElementNS(
          "http://www.w3.org/2000/svg",
          "text"
        );
        label.setAttribute("x", midX);
        label.setAttribute("y", midY - 10);
        label.setAttribute("text-anchor", "middle");
        label.setAttribute("fill", this.options.colors.edge.conditional);
        label.setAttribute("font-size", "12px");
        label.textContent = edge.label;

        const labelBg = document.createElementNS(
          "http://www.w3.org/2000/svg",
          "rect"
        );
        labelBg.setAttribute("x", midX - 30);
        labelBg.setAttribute("y", midY - 22);
        labelBg.setAttribute("width", "60");
        labelBg.setAttribute("height", "16");
        labelBg.setAttribute("fill", "white");
        labelBg.setAttribute("opacity", "0.7");
        labelBg.setAttribute("rx", "3");

        this.svg.appendChild(labelBg);
        this.svg.appendChild(label);
      }

      // Add to SVG
      this.svg.appendChild(path);

      // Store reference to edge elements
      if (!this.edgeElements[edge.source]) {
        this.edgeElements[edge.source] = {};
      }
      this.edgeElements[edge.source][edge.target] = path;
    });
  }

  getNodeColor(node) {
    const { colors } = this.options;

    if (this.currentState && this.currentState.currentNode === node.id) {
      return colors.node.current;
    }

    if (node.status === "active") {
      return colors.node.active;
    }

    if (node.status === "completed") {
      return colors.node.completed;
    }

    return colors.node.default;
  }

  getEdgeColor(edge) {
    const { colors } = this.options;

    if (edge.active) {
      return colors.edge.active;
    }

    if (edge.type === "conditional") {
      return colors.edge.conditional;
    }

    return colors.edge.default;
  }

  updateState(state) {
    this.currentState = state;

    if (!this.graphData || !this.graphData.nodes) {
      return;
    }

    // Update node colors
    this.graphData.nodes.forEach((node) => {
      const element = this.nodeElements[node.id];
      if (!element) return;

      const circle = element.querySelector("circle");
      if (circle) {
        circle.setAttribute("fill", this.getNodeColor(node));
      }
    });

    // Update edge colors
    this.graphData.edges.forEach((edge) => {
      const element = this.edgeElements[edge.source]?.[edge.target];
      if (!element) return;

      element.setAttribute("stroke", this.getEdgeColor(edge));
    });
  }

  onNodeHover(node) {
    // Highlight node on hover
    const element = this.nodeElements[node.id];
    if (element) {
      const circle = element.querySelector("circle");
      if (circle) {
        circle.setAttribute("stroke-width", "4");

        // Create tooltip
        const tooltip = document.createElementNS(
          "http://www.w3.org/2000/svg",
          "g"
        );
        tooltip.setAttribute("class", "tooltip");

        const tooltipBg = document.createElementNS(
          "http://www.w3.org/2000/svg",
          "rect"
        );
        tooltipBg.setAttribute("x", node.x + this.options.nodeRadius + 10);
        tooltipBg.setAttribute("y", node.y - 40);
        tooltipBg.setAttribute("width", "180");
        tooltipBg.setAttribute("height", "80");
        tooltipBg.setAttribute("fill", "white");
        tooltipBg.setAttribute("opacity", "0.9");
        tooltipBg.setAttribute("rx", "5");
        tooltipBg.setAttribute("stroke", "#bdc3c7");
        tooltipBg.setAttribute("stroke-width", "1");

        const tooltipTitle = document.createElementNS(
          "http://www.w3.org/2000/svg",
          "text"
        );
        tooltipTitle.setAttribute("x", node.x + this.options.nodeRadius + 20);
        tooltipTitle.setAttribute("y", node.y - 20);
        tooltipTitle.setAttribute("fill", "#2c3e50");
        tooltipTitle.setAttribute("font-size", "14px");
        tooltipTitle.setAttribute("font-weight", "bold");
        tooltipTitle.textContent = node.name;

        const tooltipDesc = document.createElementNS(
          "http://www.w3.org/2000/svg",
          "text"
        );
        tooltipDesc.setAttribute("x", node.x + this.options.nodeRadius + 20);
        tooltipDesc.setAttribute("y", node.y);
        tooltipDesc.setAttribute("fill", "#7f8c8d");
        tooltipDesc.setAttribute("font-size", "12px");
        tooltipDesc.textContent = node.description || "No description";

        const tooltipStatus = document.createElementNS(
          "http://www.w3.org/2000/svg",
          "text"
        );
        tooltipStatus.setAttribute("x", node.x + this.options.nodeRadius + 20);
        tooltipStatus.setAttribute("y", node.y + 20);
        tooltipStatus.setAttribute("fill", "#7f8c8d");
        tooltipStatus.setAttribute("font-size", "12px");
        tooltipStatus.textContent = `Status: ${node.status || "unknown"}`;

        tooltip.appendChild(tooltipBg);
        tooltip.appendChild(tooltipTitle);
        tooltip.appendChild(tooltipDesc);
        tooltip.appendChild(tooltipStatus);

        element.appendChild(tooltip);
      }
    }
  }

  onNodeLeave(node) {
    // Remove highlight on mouse leave
    const element = this.nodeElements[node.id];
    if (element) {
      const circle = element.querySelector("circle");
      if (circle) {
        circle.setAttribute("stroke-width", "2");
      }

      // Remove tooltip
      const tooltip = element.querySelector(".tooltip");
      if (tooltip) {
        element.removeChild(tooltip);
      }
    }
  }

  renderEmptyState() {
    // Clear SVG
    while (this.svg.firstChild) {
      this.svg.removeChild(this.svg.firstChild);
    }

    // Add empty state message
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", "50%");
    text.setAttribute("y", "50%");
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("fill", "#7f8c8d");
    text.setAttribute("font-size", "16px");
    text.textContent = "No graph data available";

    this.svg.appendChild(text);
  }
}

// Example graph data
const exampleGraphData = {
  nodes: [
    {
      id: "goal_generator",
      name: "Goal Generator",
      status: "completed",
      isEntry: true,
      description: "Generates or refines goals based on input",
    },
    {
      id: "planner",
      name: "Planner",
      status: "completed",
      description: "Creates a plan to achieve goals",
    },
    {
      id: "action",
      name: "Action",
      status: "active",
      description: "Executes actions based on the plan",
    },
    {
      id: "memory",
      name: "Memory",
      status: "pending",
      description: "Records events and updates memory",
    },
    {
      id: "goal_completion",
      name: "Goal Check",
      status: "pending",
      description: "Checks if goal is completed",
    },
    {
      id: "end",
      name: "End",
      status: "pending",
      description: "Workflow completion",
    },
  ],
  edges: [
    { source: "goal_generator", target: "planner", active: true },
    { source: "planner", target: "action", active: true },
    { source: "action", target: "memory", active: false },
    { source: "memory", target: "goal_completion", active: false },
    {
      source: "goal_completion",
      target: "goal_generator",
      type: "conditional",
      label: "continue",
      active: false,
    },
    {
      source: "goal_completion",
      target: "end",
      type: "conditional",
      label: "exit",
      active: false,
    },
  ],
};

// Export for use in other modules
if (typeof module !== "undefined") {
  module.exports = { LangGraphVisualizer, exampleGraphData };
}
