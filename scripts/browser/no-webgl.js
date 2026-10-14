const originalContext = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(type, ...args) {
  if (String(type).includes('webgl')) return null;
  return originalContext.call(this, type, ...args);
};
