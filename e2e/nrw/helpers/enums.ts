export enum HttpMethod {
  get = 'GET',
  post = 'POST',
}

export enum MockScenario {
  noEvents = 'no-events',
  events = 'events',
}

export enum HazardType {
  floods = 'floods',
  drought = 'drought',
  tropicalCyclone = 'tropicalCyclone',
}

/** Layer names as used in the `layers` URL parameter. */
export enum LayerName {
  exposedPopulation = 'exposedPopulation',
  floodDepth = 'floodDepth',
}
