const WebpackObfuscator = require('webpack-obfuscator');

module.exports = function override(config, env) {
  if (env === 'production') {
    config.plugins.push(
      new WebpackObfuscator({
        rotateStringArray: true
      }, [])
    );
  }
  return config;
};