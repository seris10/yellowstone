const format = value => Number(value).toLocaleString('en-US');

export const copy = {
  unavailable: 'No value available',
  webglUnavailable: 'This browser could not open the 3D view. It needs WebGL 2. The data and source notes are still available below.',
  failure: error => `The view could not load: ${error.message}. Try reloading the page. The data and source notes are still available.`,
  terrainSupport: spec => `${spec.spacing_m} m terrain · ${spec.normal?.spacing_m ?? spec.source_spacing_m} m shading detail`,
  extentLabel: extent => extent === 'core' ? '1.28 km across' : '4.1 km across',
  snapshot: () => 'Saved simulation · drag the timeline to compare temperatures.',
  runDetails: (manifest, frameCount) => `Run ${manifest.build_id}. ${format(frameCount)} saved steps. Started ${manifest.start_utc}. Playback uses the stored values at each step.`,
  sourceLabel: 'Source',
  supportLabel: 'About this layer',
  limitLabel: 'Notes',
  sourceDetailsLabel: 'Data and method',
  resolutionLabel: 'Terrain spacing',
  acquisitionLabel: 'Survey date',
  scaleLabel: 'Vertical scale',
  spacing: spec => `${spec.spacing_m} m grid, from ${spec.source_spacing_m} m elevation data`,
  verticalScale: value => Number(value) === 1 ? 'True scale' : `${value}× height exaggeration`,
  chainageLabel: 'Distance along river',
  modelTimeLabel: 'Simulation time',
  validationLabel: 'Field comparison',
  validation: 'Not yet checked against field temperature measurements.',
  crownHeightLabel: 'Height above ground',
  crownAreaLabel: 'Detected crown area',
  crownRadiusLabel: 'Radius of an equal-area circle',
  crownCountLabel: 'Tree crowns in dataset',
  crownCount: count => `${format(count)} detected crowns`,
  poolTemperatureLabel: 'Center temperature',
  poolDepthLabel: 'Depth estimate',
  poolColorLabel: 'Pool color',
  poolColor: 'Illustrative tint. It does not show temperature or microbial communities.',
  routeKindLabel: 'Route type',
  coordinateLabel: 'UTM coordinate',
  modelElevationLabel: 'Model elevation',
  terrainElevationLabel: 'Terrain elevation',
  outsideTerrain: 'Outside this terrain view',
  chartAria: 'River temperature in degrees Celsius over elapsed simulation time',
  chartCaption: 'Temperature at this river location over the saved run. The vertical line marks the selected time; gaps indicate missing values.',
  playAria: 'Play river temperature simulation',
  pauseAria: 'Pause river temperature simulation',
  drainageDescription: 'Downhill paths calculated from the elevation data. They show where runoff could collect; they are not a survey of flowing streams.',
};

export function featureName(row, type, index = 0) {
  const name = row?.name?.trim();
  if (name) return name;
  if (type === 'river') return `Firehole River · section ${index + 1}`;
  if (type === 'canopy') return `Tree crown ${index + 1}`;
  if (type === 'pools') return `Unnamed pool or lake ${index + 1}`;
  if (type === 'routes') return `Unnamed ${row?.kind || 'route'} ${index + 1}`;
  if (type === 'drainage') return `Drainage path ${index + 1}`;
  return `Unnamed waterway ${index + 1}`;
}

export function basisLabel(value) {
  const labels = {
    authored: 'estimated for this simulation',
    measured_literature: 'from published measurements',
    literature_lower_bound: 'minimum depth from published sources',
    mapped_polygon: 'Outline from a park map',
    lidar_return_void: 'Outline estimated from gaps in LiDAR returns',
  };
  return labels[value] ?? String(value ?? 'Not recorded').replaceAll('_', ' ');
}

export function layerCopy(type, {extent, spec, row, buildId} = {}) {
  if (type === 'terrain') return {
    name: 'Terrain',
    classification: 'USGS',
    source: 'USGS 3DEP elevation data · NAVD88',
    support: 'The land surface is built from USGS elevation measurements.',
    limit: extent === 'core'
      ? 'The core uses a 1 meter elevation survey. Pool and river bottoms were not measured. Data stops at the survey edge.'
      : 'This saved USGS export combines available elevation tiles. Its original service settings and source files are recorded in the data manifest. Pool and river bottoms were not measured.',
  };
  if (type === 'river') return {
    classification: 'Simulation',
    source: `River heat-transport model · run ${buildId}`,
    support: 'Each river section has one temperature at each saved time. Playback shows those stored values.',
    limit: 'Flow and upstream temperature are set for this example. River widths and depths are estimates; the colored line is drawn wide enough to see and does not show measured banks.',
  };
  if (type === 'canopy') return {
    classification: 'LiDAR',
    source: 'USGS 2020 LiDAR · 0.5 meter canopy grid',
    support: 'Tree crowns are estimated around peaks in the canopy. The displayed circles match the area of each detected crown core.',
    limit: 'Overlapping crowns and trees below the canopy can be missed. These results have not been independently checked against a field tree survey and do not identify species or full crown widths.',
  };
  if (type === 'drainage') return {
    classification: 'Estimated',
    source: 'Downhill routing of the USGS elevation grid',
    support: copy.drainageDescription,
    limit: 'Only terrain inside this map contributes to these paths. The result depends on grid spacing and how depressions are handled; it does not measure flow or define the full watershed.',
  };
  if (type === 'pools') return {
    classification: row?.outline_basis === 'lidar_return_void' ? 'LiDAR' : 'Mapped',
    source: row?.outline_basis === 'lidar_return_void' ? 'Outline estimated from gaps in LiDAR returns' : 'NPS Yellowstone GIS',
    support: row?.outline_basis === 'lidar_return_void'
      ? 'Water often leaves gaps in LiDAR returns. This outline follows one of those gaps.'
      : 'The outline follows the park map and is placed on the displayed terrain.',
    limit: 'The outline shows a surface boundary. Underwater shape and depth were not surveyed for this view.',
  };
  return {
    classification: 'Mapped',
    source: 'NPS Yellowstone GIS',
    support: type === 'routes' ? 'Trail and road lines from park mapping, placed on the displayed terrain.' : 'Waterway lines from park mapping, placed on the displayed terrain.',
    limit: type === 'routes' ? 'These maps show route locations, not current access or trail conditions.' : 'The lines show mapped locations. Their display width does not represent river width, depth or flow.',
  };
}
