package `in`.gov.maharashtra.gramsetu

import android.Manifest
import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.view.View
import android.webkit.CookieManager
import android.webkit.DownloadListener
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import `in`.gov.maharashtra.gramsetu.R
import `in`.gov.maharashtra.gramsetu.BuildConfig
import `in`.gov.maharashtra.gramsetu.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private var fileUploadCallback: ValueCallback<Array<Uri>>? = null
    private var pendingDownloadUrl: String? = null
    private var pendingDownloadMime: String? = null
    private var pendingDownloadDisposition: String? = null

    private val fileChooserLauncher: ActivityResultLauncher<Intent> =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (fileUploadCallback == null) return@registerForActivityResult

            val results: Array<Uri>? = if (result.resultCode == RESULT_OK) {
                result.data?.let { data ->
                    val clipData = data.clipData
                    if (clipData != null && clipData.itemCount > 0) {
                        Array(clipData.itemCount) { i -> clipData.getItemAt(i).uri }
                    } else {
                        data.data?.let { arrayOf(it) }
                    }
                }
            } else {
                null
            }
            fileUploadCallback?.onReceiveValue(results)
            fileUploadCallback = null
        }

    private val storagePermissionLauncher: ActivityResultLauncher<String> =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { isGranted ->
            if (isGranted) {
                pendingDownloadUrl?.let { url ->
                    executeDownload(url, pendingDownloadMime, pendingDownloadDisposition)
                }
            } else {
                Toast.makeText(this, R.string.permission_denied, Toast.LENGTH_SHORT).show()
            }
            pendingDownloadUrl = null
            pendingDownloadMime = null
            pendingDownloadDisposition = null
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        // Install Android 12+ Splash Screen
        installSplashScreen()

        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupSwipeRefresh()
        setupWebView()
        setupOfflineView()
        setupBackNavigation()

        loadInitialUrl()
    }

    private fun setupSwipeRefresh() {
        binding.swipeRefresh.setColorSchemeResources(
            R.color.primary,
            R.color.accent,
            R.color.primary_dark
        )
        binding.swipeRefresh.setOnRefreshListener {
            if (isNetworkAvailable()) {
                binding.webView.reload()
            } else {
                binding.swipeRefresh.isRefreshing = false
                showOfflineView()
            }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val webView = binding.webView
        val settings = webView.settings

        // 1. Enable standard web app capabilities
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.useWideViewPort = true
        settings.loadWithOverviewMode = true
        settings.displayZoomControls = false
        settings.builtInZoomControls = true
        settings.setSupportZoom(true)

        // 2. Official App User-Agent Customization
        val defaultUa = settings.userAgentString
        settings.userAgentString = "$defaultUa GramSetuAndroid/1.0.0 (in.gov.maharashtra.gramsetu)"

        // 3. Government Security Hardening: Prevent file:// URI exploitation
        settings.allowFileAccess = false
        settings.allowContentAccess = false
        settings.allowFileAccessFromFileURLs = false
        settings.allowUniversalAccessFromFileURLs = false

        // 4. Safe Browsing
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            settings.safeBrowsingEnabled = true
        }

        // 5. Mixed Content Settings for Local Staging Compatibility
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
        }

        // 6. Cookie Manager
        val cookieManager = CookieManager.getInstance()
        cookieManager.setAcceptCookie(true)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            cookieManager.setAcceptThirdPartyCookies(webView, true)
        }

        // 7. WebChromeClient for Progress & File Uploads
        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                if (newProgress < 100) {
                    binding.progressBar.visibility = View.VISIBLE
                    binding.progressBar.progress = newProgress
                } else {
                    binding.progressBar.visibility = View.GONE
                    binding.swipeRefresh.isRefreshing = false
                }
            }

            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                fileUploadCallback?.onReceiveValue(null)
                fileUploadCallback = filePathCallback

                val intent = fileChooserParams?.createIntent() ?: Intent(Intent.ACTION_GET_CONTENT).apply {
                    type = "*/*"
                    addCategory(Intent.CATEGORY_OPENABLE)
                }

                try {
                    fileChooserLauncher.launch(intent)
                } catch (e: Exception) {
                    fileUploadCallback?.onReceiveValue(null)
                    fileUploadCallback = null
                    Toast.makeText(this@MainActivity, "Unable to open file picker", Toast.LENGTH_SHORT).show()
                    return false
                }
                return true
            }
        }

        // 8. WebViewClient for Security Routing & Error Handling
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView?,
                request: WebResourceRequest?
            ): Boolean {
                val uri = request?.url ?: return false
                val urlString = uri.toString()

                // Special protocols: tel:, mailto:, sms:, geo:
                if (uri.scheme == "tel") {
                    startActivity(Intent(Intent.ACTION_DIAL, uri))
                    return true
                }
                if (uri.scheme == "mailto") {
                    startActivity(Intent(Intent.ACTION_SENDTO, uri))
                    return true
                }

                // Check host domain security
                val host = uri.host ?: ""
                val isInternalHost = host.contains("localhost") ||
                        host.contains("10.0.2.2") ||
                        host.contains("127.0.0.1") ||
                        host.contains("gramsetu") ||
                        host.endsWith(".gov.in")

                if (isInternalHost) {
                    return false // Let WebView load it
                }

                // External links open securely in external system browser
                try {
                    val browserIntent = Intent(Intent.ACTION_VIEW, uri)
                    startActivity(browserIntent)
                    Toast.makeText(this@MainActivity, R.string.external_link_warning, Toast.LENGTH_SHORT).show()
                    return true
                } catch (e: Exception) {
                    return false
                }
            }

            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                super.onPageStarted(view, url, favicon)
                binding.progressBar.visibility = View.VISIBLE
                binding.offlineLayout.visibility = View.GONE
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                binding.progressBar.visibility = View.GONE
                binding.swipeRefresh.isRefreshing = false
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    showOfflineView()
                }
            }

            override fun onReceivedHttpError(
                view: WebView?,
                request: WebResourceRequest?,
                errorResponse: WebResourceResponse?
            ) {
                super.onReceivedHttpError(view, request, errorResponse)
                if (request?.isForMainFrame == true && (errorResponse?.statusCode ?: 200) >= 500) {
                    showOfflineView()
                }
            }
        }

        // 9. Download Listener for Public Circulars, GRs, and Records
        webView.setDownloadListener(DownloadListener { url, userAgent, contentDisposition, mimetype, contentLength ->
            handleFileDownload(url, mimetype, contentDisposition)
        })
    }

    private fun handleFileDownload(url: String, mimetype: String?, contentDisposition: String?) {
        if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.P) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE)
                != PackageManager.PERMISSION_GRANTED
            ) {
                pendingDownloadUrl = url
                pendingDownloadMime = mimetype
                pendingDownloadDisposition = contentDisposition
                storagePermissionLauncher.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                return
            }
        }
        executeDownload(url, mimetype, contentDisposition)
    }

    private fun executeDownload(url: String, mimetype: String?, contentDisposition: String?) {
        try {
            val filename = URLUtil.guessFileName(url, contentDisposition, mimetype)
            val request = DownloadManager.Request(Uri.parse(url)).apply {
                setMimeType(mimetype)
                addRequestHeader("User-Agent", binding.webView.settings.userAgentString)
                val cookie = CookieManager.getInstance().getCookie(url)
                if (cookie != null) {
                    addRequestHeader("Cookie", cookie)
                }
                setDescription(getString(R.string.downloading_file))
                setTitle(filename)
                setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename)
            }

            val dm = getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
            dm.enqueue(request)
            Toast.makeText(this, "${getString(R.string.downloading_file)}: $filename", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            // Fallback to opening via external browser
            try {
                val browserIntent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                startActivity(browserIntent)
            } catch (e2: Exception) {
                Toast.makeText(this, R.string.download_failed, Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun setupOfflineView() {
        binding.btnRetry.setOnClickListener {
            if (isNetworkAvailable()) {
                binding.offlineLayout.visibility = View.GONE
                binding.webView.visibility = View.VISIBLE
                val urlToLoad = binding.webView.url ?: getTargetBaseUrl()
                binding.webView.loadUrl(urlToLoad)
            } else {
                Toast.makeText(this, R.string.offline_title, Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun showOfflineView() {
        binding.progressBar.visibility = View.GONE
        binding.swipeRefresh.isRefreshing = false
        binding.webView.visibility = View.GONE
        binding.offlineLayout.visibility = View.VISIBLE
    }

    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (binding.offlineLayout.visibility == View.VISIBLE) {
                    if (binding.webView.canGoBack()) {
                        binding.offlineLayout.visibility = View.GONE
                        binding.webView.visibility = View.VISIBLE
                        binding.webView.goBack()
                        return
                    }
                }

                if (binding.webView.canGoBack()) {
                    binding.webView.goBack()
                } else {
                    showExitDialog()
                }
            }
        })
    }

    private fun showExitDialog() {
        AlertDialog.Builder(this)
            .setTitle(R.string.exit_confirm_title)
            .setMessage(R.string.exit_confirm_message)
            .setPositiveButton(R.string.yes) { _, _ -> finish() }
            .setNegativeButton(R.string.no, null)
            .show()
    }

    private fun loadInitialUrl() {
        val targetUrl = getTargetBaseUrl()
        if (isNetworkAvailable()) {
            binding.offlineLayout.visibility = View.GONE
            binding.webView.visibility = View.VISIBLE
            binding.webView.loadUrl(targetUrl)
        } else {
            showOfflineView()
        }
    }

    private fun getTargetBaseUrl(): String {
        intent?.data?.let { dataUri ->
            if (dataUri.scheme == "gramsetu") {
                val path = dataUri.path ?: ""
                return "${BuildConfig.WEBVIEW_BASE_URL}$path"
            }
            if (dataUri.scheme == "http" || dataUri.scheme == "https") {
                return dataUri.toString()
            }
        }
        return BuildConfig.WEBVIEW_BASE_URL
    }

    private fun isNetworkAvailable(): Boolean {
        val connectivityManager =
            getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return false
        val activeNetwork = connectivityManager.activeNetwork ?: return false
        val capabilities = connectivityManager.getNetworkCapabilities(activeNetwork) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    override fun onDestroy() {
        binding.webView.destroy()
        super.onDestroy()
    }
}
