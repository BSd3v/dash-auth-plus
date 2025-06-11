const path = require('path');

module.exports = {
  entry: './src/ts/index.ts',
  output: {
    path: path.resolve(__dirname, 'dash_auth_plus_components'),
    filename: 'dash_auth_plus.js',
    library: 'dash_auth_plus_components',
    libraryTarget: 'umd',
    umdNamedDefine: true,
    globalObject: 'this',
  },
  resolve: {
    extensions: ['.ts', '.tsx', '.js', '.jsx'],
  },
  module: {
    rules: [
      {
        test: /\.(ts|tsx)$/,
        use: 'ts-loader',
        exclude: /node_modules/,
      },
      {
        test: /\.(js|jsx)$/,
        use: 'babel-loader',
        exclude: /node_modules/,
      },
    ],
  },
  externals: {
    react: 'React',
    'react-dom': 'ReactDOM',
  },
  devtool: 'source-map',
};

