module.exports = {
    webpack: {
        configure: {
            resolve: {
                fallback: {
                    "path": require.resolve("path-browserify"),
                    "os": require.resolve("os-browserify/browser"),
                    "crypto": require.resolve("crypto-browserify"),
                    "stream": require.resolve("stream-browserify"),
                    "buffer": require.resolve("buffer/"),
                    "util": require.resolve("util/"),
                    "assert": require.resolve("assert/"),
                    "http": require.resolve("stream-http"),
                    "https": require.resolve("https-browserify"),
                    "zlib": require.resolve("browserify-zlib"),
                    "url": require.resolve("url/")
                }
            }
        }
    }
}; 