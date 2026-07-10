import React from 'react';
// macDiag Modern — line-icon set (Lucide path data, 1.75px stroke, no fill).
// A deliberate modern addition over the source app (which had no icon set);
// chosen to match the premium/engineering tone. Single consistent stroke style.
const ICON_PATHS = {
  gauge:    ["m12 14 4-4", "M3.34 19a10 10 0 1 1 17.32 0"],
  activity: ["M22 12h-4l-3 9L9 3l-3 9H2"],
  alert:    ["m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z", "M12 9v4", "M12 17h.01"],
  cpu:      ["M12 20v2","M12 2v2","M17 20v2","M17 2v2","M2 12h2","M2 17h2","M2 7h2","M20 12h2","M20 17h2","M20 7h2","M7 20v2","M7 2v2","__rect4x4","__rect8x8"],
  sliders:  ["M21 4h-7","M10 4H3","M21 12h-9","M8 12H3","M21 20h-5","M12 20H3","M14 2v4","M8 10v4","M16 18v4"],
  car:      ["M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2","__c7","__c17"],
  zap:      ["M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"],
  sun:      ["M12 2v2","M12 20v2","m4.93 4.93 1.41 1.41","m17.66 17.66 1.41 1.41","M2 12h2","M20 12h2","m6.34 17.66-1.41 1.41","m19.07 4.93-1.41 1.41","__csun"],
  moon:     ["M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"],
  search:   ["m21 21-4.3-4.3","__csearch"],
  power:    ["M12 2v10","M18.4 6.6a9 9 0 1 1-12.77.04"],
  chevron:  ["m9 18 6-6-6-6"],
  menu:     ["M4 12h16","M4 6h16","M4 18h16"],
  x:        ["M18 6 6 18","m6 6 12 12"],
  refresh:  ["M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8","M21 3v5h-5","M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16","M8 16H3v5"],
  check:    ["M20 6 9 17l-5-5"],
  download: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4","M7 10l5 5 5-5","M12 15V3"],
  upload:   ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4","M17 8l-5-5-5 5","M12 3v12"],
  drive:    ["M22 12H2","M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z","M6 16h.01","M10 16h.01"],
  book:     ["M4 19.5A2.5 2.5 0 0 1 6.5 17H20","M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"],
  globe:    ["M2 12h20","M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z","__cglobe"],
};

function Icon({ name, size = 18, style, strokeWidth = 1.75 }) {
  const parts = ICON_PATHS[name] || [];
  const extras = [];
  parts.forEach((p, i) => {
    if (p === "__cglobe") return extras.push(React.createElement("circle", { key: "cg", cx: 12, cy: 12, r: 10 }));
    if (p === "__rect4x4") extras.push(React.createElement("rect", { key: "r1", x: 4, y: 4, width: 16, height: 16, rx: 2 }));
    else if (p === "__rect8x8") extras.push(React.createElement("rect", { key: "r2", x: 8, y: 8, width: 8, height: 8, rx: 1 }));
    else if (p === "__c7") extras.push(React.createElement("circle", { key: "c1", cx: 7, cy: 17, r: 2 }));
    else if (p === "__c17") extras.push(React.createElement("circle", { key: "c2", cx: 17, cy: 17, r: 2 }));
    else if (p === "__csun") extras.push(React.createElement("circle", { key: "cs", cx: 12, cy: 12, r: 4 }));
    else if (p === "__csearch") extras.push(React.createElement("circle", { key: "cf", cx: 11, cy: 11, r: 8 }));
    else extras.push(React.createElement("path", { key: i, d: p }));
  });
  return React.createElement("svg", {
    width: size, height: size, viewBox: "0 0 24 24", fill: "none",
    stroke: "currentColor", strokeWidth, strokeLinecap: "round", strokeLinejoin: "round",
    style: { flex: "none", ...style },
  }, extras);
}

export { Icon };
