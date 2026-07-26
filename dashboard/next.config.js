/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // lean container image: bundles only what the server actually needs
  output: "standalone",
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
