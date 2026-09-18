/** Metro shim for Node builtins referenced only in Jest/Node ZIP sink. Never called on device. */
module.exports = new Proxy(
  {},
  {
    get() {
      throw new Error('Node builtin is not available in the React Native runtime');
    },
  },
);
