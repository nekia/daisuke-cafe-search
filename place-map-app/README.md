# Getting Started with Create React App

This project was bootstrapped with [Create React App](https://github.com/facebook/create-react-app).

## Available Scripts

In the project directory, you can run:

### `npm start`

Runs the app in the development mode.\
Open [http://localhost:3000](http://localhost:3000) to view it in your browser.

The page will reload when you make changes.\
You may also see any lint errors in the console.

### `npm test`

Launches the test runner in the interactive watch mode.\
See the section about [running tests](https://facebook.github.io/create-react-app/docs/running-tests) for more information.

### `npm run build`

Builds the app for production to the `build` folder.\
It correctly bundles React in production mode and optimizes the build for the best performance.

The build is minified and the filenames include the hashes.\
Your app is ready to be deployed!

See the section about [deployment](https://facebook.github.io/create-react-app/docs/deployment) for more information.

### `npm run eject`

**Note: this is a one-way operation. Once you `eject`, you can't go back!**

If you aren't satisfied with the build tool and configuration choices, you can `eject` at any time. This command will remove the single build dependency from your project.

Instead, it will copy all the configuration files and the transitive dependencies (webpack, Babel, ESLint, etc) right into your project so you have full control over them. All of the commands except `eject` will still work, but they will point to the copied scripts so you can tweak them. At this point you're on your own.

You don't have to ever use `eject`. The curated feature set is suitable for small and middle deployments, and you shouldn't feel obligated to use this feature. However we understand that this tool wouldn't be useful if you couldn't customize it when you are ready for it.

## 本番デプロイ（Firebase Hosting）

このフロントエンドは [Firebase Hosting](https://firebase.google.com/docs/hosting) に公開する想定です。`npm run build` で生成した `build/` ディレクトリの静的ファイルがそのまま配信されます。クライアントルーティング用に、`firebase.json` で全パスを `index.html` にフォールバックする SPA 設定になっています。

### 前提条件

- **Node.js**（LTS 推奨）と **npm** がインストールされていること
- **Firebase CLI**  
  `npm install -g firebase-tools`
- デプロイ先の **Firebase プロジェクト**に対する権限（Owner / Editor など）がある Google アカウント
- 初回のみ **`firebase login`** で CLI からログイン済みであること

### Firebase プロジェクト ID

このリポジトリの [`.firebaserc`](./.firebaserc) で既定プロジェクトが指定されています。

- 既定: `daisuke-cafe-search-af201`

`firebase deploy` 時に `--project` を省略すると、この `default` が使われます。別プロジェクトへ載せる場合は `.firebaserc` を更新するか、`firebase use <projectId>` / `firebase deploy --only hosting --project <projectId>` で明示してください。

### ビルド時に必要な環境変数（重要）

Create React App では、`REACT_APP_` で始まる変数は **`npm run build` 実行時** にバンドルへ埋め込まれます。本番用の値は開発用と分け、**リポジトリにコミットしない**ようにします。機密を含む場合は **`.env.production.local`** に書くと、このリポジトリの [`.gitignore`](./.gitignore) により無視されます（本番ビルドでも読み込まれます）。`.env.production` はデフォルトでは無視されないため、コミットに含めないよう注意してください。

本アプリで参照している変数は次のとおりです。

| 変数名 | 用途 |
|--------|------|
| `REACT_APP_BACKEND_ENDPOINT` | バックエンド API のベース URL（例: `https://your-api.example.com`）。末尾スラッシュは付けない想定でコード側と合わせてください。 |
| `REACT_APP_GOOGLE_CLIENT_ID` | Google ログイン用の OAuth 2.0 クライアント ID（Web アプリケーション）。 |
| `REACT_APP_GOOGLE_MAPS_API_KEY` | Google Maps JavaScript API 用の API キー。 |

**設定方法の例**

1. `place-map-app` 直下に **`.env.production`** または **`.env.production.local`** を作成し、上記を `KEY=value` 形式で記述する。  
   `npm run build` は本番ビルド時にこれらを自動で読み込みます（`.env.production.local` があれば同名キーで上書きされます）。
2. または、ビルド直前にシェルでエクスポートしてから `npm run build` する。

値が空のままビルドすると、本番サイトで API やログインが動きません。デプロイ前に必ず確認してください。

### Google Cloud コンソール側の設定（本番 URL 公開後）

本番の Hosting URL（例: `https://<project>.web.app` やカスタムドメイン）が決まったら、次を合わせて設定します。

1. **Google ログイン（OAuth）**  
   [Google Cloud Console](https://console.cloud.google.com/) → API とサービス → 認証情報 → 使用中の OAuth 2.0 クライアント（Web）→ **承認済みの JavaScript 生成元** に、本番ページのオリジン（例: `https://daisuke-cafe-search-af201.web.app`）を追加する。
2. **Maps JavaScript API キー**  
   同じく認証情報で API キーの **アプリケーションの制限** を「HTTP リファラー」などにし、本番ドメインを許可リストに含める（開発用 localhost も必要なら併記）。

バックエンドは `cors()` で広く許可しているため、フロントのオリジン追加は主に **ブラウザから Google へ直接行う OAuth / Maps** 側の設定が重要です。

### デプロイ手順

リポジトリのルートではなく、**このディレクトリ（`place-map-app`）** で実行します。

```bash
cd place-map-app

# 依存関係のインストール（初回または package-lock 更新時）
npm ci

# 本番ビルド（.env.production などで REACT_APP_* を設定済みであること）
npm run build

# Hosting のみデプロイ
firebase deploy --only hosting
```

`firebase deploy` の完了ログに **Hosting URL** が表示されます。ブラウザで開き、ログイン・地図・店舗取得が問題ないか確認してください。

**ホスティング以外はデプロイしない**

- フロントのみ更新する場合は `--only hosting` で十分です。
- Firestore / Functions などを使っていない構成であれば、誤って他サービスを触る心配も減ります。

### デプロイ後の確認チェックリスト

- [ ] 本番 URL でページが表示される
- [ ] Google ログインが完了する（許可メールアドレスのみの制限はアプリ側ロジック）
- [ ] 地図が表示される（API キーとリファラー制限）
- [ ] 店舗データが取得できる（`REACT_APP_BACKEND_ENDPOINT` とバックエンドの稼働）

### プレビュー用チャンネル（任意）

本番に影響させずに確認したい場合は、[Firebase Hosting のプレビューチャンネル](https://firebase.google.com/docs/hosting/test-preview-deploy)を利用できます。例:

```bash
npm run build
firebase hosting:channel:deploy preview-branch-name
```

### トラブルシューティング（よくある原因）

- **ビルドは成功したが API に繋がらない**  
  `REACT_APP_BACKEND_ENDPOINT` がビルド時に正しく入っているか、ブラウザの開発者ツールのネットワークタブでリクエスト先 URL を確認する。変更後は **再ビルドと再デプロイ** が必要です。
- **`firebase: command not found`**  
  `npm install -g firebase-tools` または `npx firebase-tools deploy --only hosting` を利用する。
- **403 / API キー関連**  
  OAuth の生成元、Maps キーのリファラー制限に本番 URL が含まれているか確認する。

## Learn More

You can learn more in the [Create React App documentation](https://facebook.github.io/create-react-app/docs/getting-started).

To learn React, check out the [React documentation](https://reactjs.org/).

### Code Splitting

This section has moved here: [https://facebook.github.io/create-react-app/docs/code-splitting](https://facebook.github.io/create-react-app/docs/code-splitting)

### Analyzing the Bundle Size

This section has moved here: [https://facebook.github.io/create-react-app/docs/analyzing-the-bundle-size](https://facebook.github.io/create-react-app/docs/analyzing-the-bundle-size)

### Making a Progressive Web App

This section has moved here: [https://facebook.github.io/create-react-app/docs/making-a-progressive-web-app](https://facebook.github.io/create-react-app/docs/making-a-progressive-web-app)

### Advanced Configuration

This section has moved here: [https://facebook.github.io/create-react-app/docs/advanced-configuration](https://facebook.github.io/create-react-app/docs/advanced-configuration)

### Deployment

This project: 上記の **「本番デプロイ（Firebase Hosting）」** を参照してください。  
General CRA notes: [https://facebook.github.io/create-react-app/docs/deployment](https://facebook.github.io/create-react-app/docs/deployment)

### `npm run build` fails to minify

This section has moved here: [https://facebook.github.io/create-react-app/docs/troubleshooting#npm-run-build-fails-to-minify](https://facebook.github.io/create-react-app/docs/troubleshooting#npm-run-build-fails-to-minify)
