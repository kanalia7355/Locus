import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

// These APIs are [SecureContext]-only. A page served over plain HTTP on a LAN
// address is not a secure context, so the property is absent there and a bare
// call fails. Feature-detect and provide a fallback instead.
const secureContextOnly =
  "`[SecureContext]` 専用。LAN のプレーン HTTP では存在しない。機能判定のうえで代替を用意すること。";

export default tseslint.config(
  { ignores: ["dist", "playwright-report", "test-results"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "no-restricted-properties": [
        "error",
        {
          object: "navigator",
          property: "clipboard",
          message: secureContextOnly,
        },
        {
          object: "navigator",
          property: "credentials",
          message: secureContextOnly,
        },
        {
          object: "navigator",
          property: "mediaDevices",
          message: secureContextOnly,
        },
        {
          object: "navigator",
          property: "serviceWorker",
          message: secureContextOnly,
        },
        { object: "crypto", property: "subtle", message: secureContextOnly },
        {
          object: "crypto",
          property: "randomUUID",
          message: secureContextOnly,
        },
      ],
      "no-restricted-syntax": [
        "error",
        {
          // In React this is always a JSX attribute, never a member expression.
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message:
            "dangerouslySetInnerHTML は使用禁止です。React の要素として組み立ててください。T-PH6-114 で Markdown 描画に着手するときは、この規則を再評価すること。",
        },
        {
          selector: "MemberExpression[property.name='innerHTML']",
          message:
            "innerHTML は使用禁止です。textContent や createElement で組み立ててください。",
        },
        {
          // no-restricted-properties matches the receiver's name, so an alias
          // such as `const c = globalThis.crypto; c.randomUUID()` slips past it.
          // A direct `crypto.randomUUID` is already covered above.
          selector:
            "MemberExpression[property.name='randomUUID']:not([object.name='crypto'])",
          message: secureContextOnly,
        },
      ],
    },
  },
);
