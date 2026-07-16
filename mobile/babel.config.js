module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: [
      [
        'module-resolver',
        {
          root: ['./'],
          alias: {
            '@core': './src/core',
            '@domain': './src/domain',
            '@native': './src/native',
            '@shared': './src/shared',
          },
        },
      ],
    ],
  };
};
