#include <iostream>
#include <string>
#include <regex>
#include "include/curl/curl.h"
#include <fstream>
#include <windows.h>
#include <unordered_set>
#include <filesystem>

#pragma comment(lib, "ws2_32.lib")
#pragma comment(lib, "wldap32.lib")
#pragma comment(lib, "crypt32.lib")
#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "libcurl/x64/libcurl_a_debug.lib")
#pragma comment(lib, "winmm.lib")
#pragma comment(lib, "Normaliz.lib")

std::string theip = "127.0.0.1";
std::string theport = "10809";
std::string usepx = "1";
std::string regex = "<article\n    class=\"post-card post-card--preview\"\n    data-id=\"(.*?)\"\n    data-service=\"(.*?)\"\n    data-user=\"(.*?)\"\n  >\n    <a href=\"(.*?)\">\n      <header class=\"post-card__header\">\n            (.*?)\n      </header>\n        <div class=\"post-card__image-container\">\n            <img\n              class=\"post-card__image\"\n              src=\"(.*?)\"\n            >\n          </div>\n      <footer class=\"post-card__footer\">\n              <time\n    class=\"timestamp \" \n    datetime=\"(.*?)\"\n  >\n      (.*?)\n  </time>\n\n        <div>\n            (.*?)\n        </div>\n      </footer>\n    </a>\n  </article>";
std::string tpox;
std::string dlmode;


//将传入的UTF8字符串转换为GBK返回
//WindowsAPI
std::string convertUTF8ToGBK(const std::string& utf8String) {
	int wideLength = MultiByteToWideChar(CP_UTF8, 0, utf8String.c_str(), -1, nullptr, 0);
	if (wideLength == 0) {
		std::cerr << "无法获取宽字符字符串长度！" << std::endl;
		return "";
	}

	wchar_t* wideBuffer = new wchar_t[wideLength];
	MultiByteToWideChar(CP_UTF8, 0, utf8String.c_str(), -1, wideBuffer, wideLength);

	int gbkLength = WideCharToMultiByte(CP_ACP, 0, wideBuffer, -1, nullptr, 0, nullptr, nullptr);
	if (gbkLength == 0) {
		std::cerr << "无法获取GBK编码字符串长度！" << std::endl;
		delete[] wideBuffer;
		return "";
	}

	char* gbkBuffer = new char[gbkLength];
	WideCharToMultiByte(CP_ACP, 0, wideBuffer, -1, gbkBuffer, gbkLength, nullptr, nullptr);

	std::string gbkString(gbkBuffer);

	delete[] wideBuffer;
	delete[] gbkBuffer;

	return gbkString;
}

//将传入的GBK字符串转换UTF8为返回
//WindowsAPI
std::string ConvertGBKToUTF8(const std::string& gbkText)
{
	int wideLength = ::MultiByteToWideChar(CP_ACP, 0, gbkText.c_str(), -1, NULL, 0);
	if (wideLength == 0)
	{
		std::cerr << "Failed to convert string to wide characters." << std::endl;
		return "";
	}

	std::wstring wideText;
	wideText.resize(wideLength - 1);
	if (::MultiByteToWideChar(CP_ACP, 0, gbkText.c_str(), -1, &wideText[0], wideLength) == 0)
	{
		std::cerr << "Failed to convert string to wide characters." << std::endl;
		return "";
	}

	int utf8Length = ::WideCharToMultiByte(CP_UTF8, 0, wideText.c_str(), -1, NULL, 0, NULL, NULL);
	if (utf8Length == 0)
	{
		std::cerr << "Failed to convert wide characters to UTF-8." << std::endl;
		return "";
	}

	std::string utf8Text;
	utf8Text.resize(utf8Length - 1);
	if (::WideCharToMultiByte(CP_UTF8, 0, wideText.c_str(), -1, &utf8Text[0], utf8Length, NULL, NULL) == 0)
	{
		std::cerr << "Failed to convert wide characters to UTF-8." << std::endl;
		return "";
	}

	return utf8Text;
}


// 回调函数，用于写入文件
// 结构体用于保存进度信息
struct ProgressData {
	double lastTime;
	curl_off_t lastDownloaded;
};

size_t WriteCallbackf(void* contents, size_t size, size_t nmemb, void* userp) {
	size_t total_size = size * nmemb;
	std::ofstream* file = static_cast<std::ofstream*>(userp);
	file->write(static_cast<const char*>(contents), total_size);
	return total_size;
}

int progress_func(void* ptr, double TotalToDownload, double NowDownloaded,
	double TotalToUpload, double NowUploaded)
{
	int totaldotz = 40;
	double fractiondownloaded = NowDownloaded / TotalToDownload;

	int dotz = round(fractiondownloaded * totaldotz);

	int ii = 0;
	printf("%3.0f%% [", fractiondownloaded * 100);

	for (; ii < dotz; ii++) {
		printf("=");
	}

	for (; ii < totaldotz; ii++) {
		printf(" ");
	}
	printf("]           \r");
	fflush(stdout);
	
	return 0;
}


bool myDownloadFile(const std::string& relativePath, const std::string& url, const std::string& fileName) {
	std::string filePath = convertUTF8ToGBK(relativePath) + "\\" + convertUTF8ToGBK(fileName);

	CURL* curl = curl_easy_init();
	if (curl) {
		// 打开文件
		std::ofstream file(filePath, std::ios::binary);
		if (!file) {
			std::cout << "无法打开文件：" << filePath << std::endl;
			return false;
		}

		std::string tpox = theip + ":" + theport;

		// 设置Curl选项
		curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
		curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallbackf);
		curl_easy_setopt(curl, CURLOPT_USERAGENT, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.37");
		curl_easy_setopt(curl, CURLOPT_WRITEDATA, &file);
		curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
		if (usepx == "1") {
			curl_easy_setopt(curl, CURLOPT_PROXY, tpox.c_str());
		}
		curl_easy_setopt(curl, CURLOPT_PROXYTYPE, CURLPROXY_HTTP);
		curl_easy_setopt(curl, CURLOPT_HTTPPROXYTUNNEL, 1L);

		// 设置进度回调函数
		curl_easy_setopt(curl, CURLOPT_NOPROGRESS, FALSE);
		curl_easy_setopt(curl, CURLOPT_PROGRESSFUNCTION, progress_func);
		printf("]\r");

		// 执行请求
		CURLcode res = curl_easy_perform(curl);

		int count = 0;
		// 检查请求是否成功
		while (res != CURLE_OK) {
			count++;
			if (count == 5) {
				return !true;
			}
			std::cout << "下载失败：" << curl_easy_strerror(res) << std::endl;
			std::cout << "重试…（" << count << "/5）" << std::endl;
			res = curl_easy_perform(curl);
		}

		// 清理Curl资源
		curl_easy_cleanup(curl);

		// 关闭文件
		file.close();

		std::cout << "文件下载成功：" << filePath << std::endl;
		return true;
	}

	return false;
}

// 回调函数，用于处理HTTP请求的返回数据
size_t WriteCallback(char* contents, size_t size, size_t nmemb, std::string* output) {
	size_t totalSize = size * nmemb;
	output->append(contents, totalSize);
	return totalSize;
}

// 获取指定网址的页面内容
std::string getPageContent(const std::string& url) {
	std::string response;

	// 初始化libcurl
	curl_global_init(CURL_GLOBAL_DEFAULT);
	CURL* curl = curl_easy_init();

	if (curl) {
		curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
		curl_easy_setopt(curl, CURLOPT_USERAGENT, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.37");
		curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
		curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
		curl_easy_setopt(curl, CURLOPT_ENCODING, "UTF-8");
		if (usepx == "1") {
			curl_easy_setopt(curl, CURLOPT_PROXY, tpox.c_str());
		}

		CURLcode res = curl_easy_perform(curl);

		if (res != CURLE_OK) {
			std::cerr << "curl_easy_perform() failed: " << curl_easy_strerror(res) << std::endl;
		}

		curl_easy_cleanup(curl);
	}

	curl_global_cleanup();

	return response;
}

// 提取网页内容中的artist_name
std::string extractArtistName(const std::string& webpage) {
	std::string artistName;
	std::string searchString = "<meta name=\"artist_name\" content=\"";
	size_t startPos = webpage.find(searchString);
	if (startPos != std::string::npos) {
		startPos += searchString.length();
		size_t endPos = webpage.find("\"", startPos);
		if (endPos != std::string::npos) {
			artistName = webpage.substr(startPos, endPos - startPos);
		}
	}
	return artistName;
}

// 提取artist_name
std::string getArtistName(const std::string& url) {
	std::string artistName;

	std::string tpox = theip + ":" + theport;
	CURL* curl = curl_easy_init();
	if (curl) {
		std::string webpage;
		curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
		curl_easy_setopt(curl, CURLOPT_USERAGENT, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.37");
		curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
		curl_easy_setopt(curl, CURLOPT_WRITEDATA, &webpage);
		if (usepx == "1") {
			curl_easy_setopt(curl, CURLOPT_PROXY, tpox.c_str());
		}
		curl_easy_setopt(curl, CURLOPT_PROXYTYPE, CURLPROXY_HTTP);
		curl_easy_setopt(curl, CURLOPT_HTTPPROXYTUNNEL, 1L);

		CURLcode res = curl_easy_perform(curl);
		if (res == CURLE_OK) {
			artistName = extractArtistName(webpage);
		}
		else {
			std::cerr << "Failed to retrieve webpage: " << curl_easy_strerror(res) << std::endl;
		}

		curl_easy_cleanup(curl);
	}
	else {
		std::cerr << "Failed to initialize CURL." << std::endl;
	}

	return artistName;
}

//用于将HTML转义字符转换回原样
std::string unescapeHTML(const std::string& input) {
	std::string result;
	size_t pos = 0;
	size_t len = input.length();

	while (pos < len) {
		if (input[pos] == '&') {
			size_t endPos = input.find(';', pos + 1);
			if (endPos != std::string::npos) {
				std::string escape = input.substr(pos + 1, endPos - pos - 1);

				if (escape == "amp") {
					result += '&';
				}
				if (escape == "38") {
					result += '&';
				}
				else if (escape == "lt") {
					result += '<';
				}
				else if (escape == "60") {
					result += '<';
				}
				else if (escape == "gt") {
					result += '>';
				}
				else if (escape == "62") {
					result += '>';
				}
				else if (escape == "quot") {
					result += '"';
				}
				else if (escape == "34") {
					result += '"';
				}
				else if (escape == "apos") {
					result += '\'';
				}
				else if (escape == "39") {
					result += '\'';
				}
				// 添加更多转义字符的处理逻辑

				pos = endPos + 1;
				continue;
			}
		}

		result += input[pos];
		pos++;
	}

	return result;
}

//将传入的字符串的换行变成\n
//测试用
void replaceNewlines(std::string& str) {
	size_t found = str.find('\n');
	while (found != std::string::npos) {
		str.replace(found, 1, "\\n");
		found = str.find('\n', found + 2); // 找到下一个换行符
	}
}

//将传入的字符串写入到运行目录下的out.txt
//测试用
void writeToFile(const std::string& content) {
	std::ofstream outputFile("out.txt");

	if (outputFile.is_open()) {
		outputFile << content;
		outputFile.close();
		std::cout << "写入文件成功！" << std::endl;
	}
	else {
		std::cerr << "无法打开文件！" << std::endl;
	}
}

//vector去重
void removeDuplicates(std::vector<std::string>& urls) {
	std::unordered_set<std::string> uniqueUrls;
	std::vector<std::string> result;

	for (const std::string& url : urls) {
		if (uniqueUrls.find(url) == uniqueUrls.end()) {
			// 当前元素在集合中不存在，添加到结果向量和唯一元素集合
			result.push_back(url);
			uniqueUrls.insert(url);
		}
	}

	urls = result;
}

//替换非法Windows字符
std::string ReplaceInvalidChars(std::string str) {
	std::string invalidChars = "\\/*?\"<>|:";
	for (auto& c : str) {
		size_t found = invalidChars.find(c);
		if (found != std::string::npos) {
			c = '_';
		}
	}
	return str;
}

//创建并写入文件
bool myCreateFile(const std::string& relativePath, const std::string& fileName, const std::string& content)
{
	// 创建完整的文件路径
	std::filesystem::path filePath(convertUTF8ToGBK(relativePath));

	filePath /= fileName;

	// 打开文件流进行写入
	std::ofstream file(filePath);
	if (file.is_open())
	{
		file << content;
		file.close();
		std::cout << "文件创建成功：" << fileName << std::endl;
		return true;
	}
	else
	{
		std::cout << "文件创建失败：" << fileName << std::endl;
		return false;
	}
}

//创建文件夹
//WindowsAPI
bool CreateDirectoryRecursive(const std::wstring& path)
{
	if (::CreateDirectoryW(path.c_str(), NULL) || ::GetLastError() == ERROR_ALREADY_EXISTS)
	{
		std::wcout << L"文件夹创建成功" << std::endl;
		return true;
	}
	else
	{
		DWORD lastError = ::GetLastError();
		if (lastError == ERROR_PATH_NOT_FOUND)
		{
			// 递归创建上级目录
			size_t pos = path.find_last_of(L"\\/");
			if (pos != std::wstring::npos)
			{
				std::wstring parentPath = path.substr(0, pos);
				if (CreateDirectoryRecursive(parentPath))
				{
					// 创建上级目录成功后再次尝试创建当前目录
					return CreateDirectoryRecursive(path);
				}
				else
				{
					return false;
				}
			}
		}

		std::wcerr << L"文件夹创建失败: " << path << std::endl;
		return false;
	}
}
bool myCreateDirectory(const std::string& relativePath)
{
	std::wstring widePath;
	int bufferSize = ::MultiByteToWideChar(CP_UTF8, 0, relativePath.c_str(), -1, nullptr, 0);
	if (bufferSize > 0)
	{
		widePath.resize(bufferSize);
		::MultiByteToWideChar(CP_UTF8, 0, relativePath.c_str(), -1, &widePath[0], bufferSize);
	}

	return CreateDirectoryRecursive(widePath);
}

//提取后缀名
std::string GetFileExtension(const std::string& downloadLink)
{
	std::string fileExtension;

	// 找到最后一个斜杠的位置
	size_t lastSlashPos = downloadLink.find_last_of("/");
	if (lastSlashPos != std::string::npos)
	{
		// 提取文件名
		std::string fileName = downloadLink.substr(lastSlashPos + 1);

		// 找到最后一个点的位置
		size_t lastDotPos = fileName.find_last_of(".");
		if (lastDotPos != std::string::npos && lastDotPos != fileName.length() - 1)
		{
			// 提取后缀名
			fileExtension = fileName.substr(lastDotPos + 1);
		}
	}

	return fileExtension;
}

//从尾部删字符
std::string RemoveLastCharacters(const std::string& str, size_t n)
{
	if (n >= str.length()) {
		return "";
	}

	return str.substr(0, str.length() - n);
}

// 提取标题内容和URL
void extractTitleAndURL(const std::string& url, std::string& title, std::string& pubDate, std::string& content, std::vector<std::string>& urls) {
	std::string response;
	response = getPageContent(url);
	//response = convertUTF8ToGBK(response);
	response = unescapeHTML(response);
	//replaceNewlines(response);
	//writeToFile(response);

	// 提取标题内容
	std::regex titleRegex("<h1 class=\"post__title\">\n            <span>(.*?)</span> <span>((.*?))</span>\n        </h1>");
	std::smatch titleMatch;
	if (std::regex_search(response, titleMatch, titleRegex) && titleMatch.size() > 1) {
		title = titleMatch[1].str();
	}

	// 提取发布时间
	std::regex pubDateRegex("<meta name=\"published\" content=\"(.*?)\">");
	std::smatch pubDateMatch;
	if (std::regex_search(response, pubDateMatch, pubDateRegex) && pubDateMatch.size() > 1) {
		pubDate = pubDateMatch[1].str();
	}

	// 提取说明内容
	std::regex contentRegex("<h2>Content</h2>\n    <div class=\"post__content\">\n<pre>([\\s\\S]*?)</pre>\n    </div>");
	std::smatch contentMatch;
	if (std::regex_search(response, contentMatch, contentRegex) && contentMatch.size() > 1) {
		content = contentMatch[1].str();
	}

	// 提取格式为<a class="fileThumb" href="#url" download="#filename">的URL部分
	std::regex urlRegex("<a\n              class=\"fileThumb\"\n              href=\"(.*?)\"\n              download=\".*?\"\n            >");
	std::sregex_iterator urlIterator(response.begin(), response.end(), urlRegex);
	std::sregex_iterator endIterator;
	for (; urlIterator != endIterator; ++urlIterator) {
		urls.push_back((*urlIterator)[1].str());
	}

}
// 从目录提取投稿
void extractArticalLink(const std::string& url, std::vector<std::string>& urls) {
	int offset = 0;
	int count = 1;
	std::cout << "开始获取目录…" << std::endl;
	std::string fullUrl = url + "?o=" + std::to_string(offset);

	while (true) {
		std::string content = getPageContent(fullUrl);
		if (content.find("Redirecting...") != std::string::npos) {
			// 当返回内容中包含 "Redirecting..." 时，结束循环
			break;
		}
		std::cout << "正在获取第" << count << "页" << std::endl;
		count++;
		// 使用正则表达式提取链接部分
		std::regex linkRegex(regex);
		std::smatch match;

		// 在返回内容中查找匹配的链接并添加到 urls 中
		std::string::const_iterator searchStart(content.cbegin());
		while (std::regex_search(searchStart, content.cend(), match, linkRegex)) {
			urls.push_back(match[4]);
			searchStart = match.suffix().first;
		}

		// 增加 offset 值，构造下一个请求的 URL
		offset += 50;
		fullUrl = url + "?o=" + std::to_string(offset);
	}
}


int main() {
	std::cout << "Ver. 1.2.4" << std::endl;
	//Single版警告
	//std::cout << "注意：本程序仅下载单篇投稿" << std::endl;
	std::cout << "你要使用HTTP代理吗？不使用输入n，使用请留空直接回车即可：" << std::endl;
	std::getline(std::cin, usepx);
	if (usepx != "n") {
		usepx = "1";
		std::cout << "您选择使用HTTP代理" << std::endl;
		std::cout << "请输入HTTP代理ip(留空为默认localhost，推荐)：" << std::endl;
		std::string tip = "";
		std::getline(std::cin, tip);
		std::cout << "请输入HTTP代理端口(留空为默认10809，10809为V2rayN默认端口，请根据您的代理软件选择)：" << std::endl;
		std::string tport = "";
		std::getline(std::cin, tport);
		if (tip != "") { theip = tip; }
		if (tport != "") { theport = tport; }
		tpox = theip + ":" + theport;
		std::cout << "您的HTTP代理地址是：" << tpox << std::endl;
	}
	std::cout << "是否使用仅图片下载模式？该模式下将只会下载图片，且所有图片均存储在同一目录下。使用请输入y，不使用请留空：" << std::endl;
	std::getline(std::cin, dlmode);
	if (dlmode == "y") {
		dlmode = "1";
	}
	else if (dlmode == "yx") {
		dlmode = "1";
		std::getline(std::cin, regex);
	}
	else if (dlmode == "x") {
		std::getline(std::cin, regex);
		dlmode = "0";
	}
	else{
		dlmode = "0";
	}
	const std::string domain = "https://kemono.su";
	std::string targetUrl = "";
	std::cout << "请输入目标网址（请不要输入“?o=”及之后的部分，否则程序将无法正常识别）：" << std::endl;
	std::getline(std::cin, targetUrl);

	/*
	 单个下载STR
	
	std::string theName = "";
	std::cout << "请输入作者名称：" << std::endl;
	std::getline(std::cin, theName);
	std::string title;
	std::string pubDate;
	std::string content;
	std::vector<std::string> urls;
	extractTitleAndURL(targetUrl, title, pubDate, content, urls);
	title = ReplaceInvalidChars(title);
	pubDate = RemoveLastCharacters(pubDate, 9);
	std::string thePath;
	if (dlmode == "0") {
		thePath = ReplaceInvalidChars(theName) + "\\(" + pubDate + ")" + ReplaceInvalidChars(title);
	}
	else {
		thePath = ReplaceInvalidChars(theName);
	}
	myCreateDirectory(thePath);
	if (dlmode == "0") {
		myCreateFile(thePath, "ReadMe.txt", content);
	}
	int tcount = 1;
	for (const auto& turl : urls) {
		std::cout << "正在下载第" << tcount << "张图片" << std::endl;
		if (dlmode == "0") {
			myDownloadFile(thePath, turl, std::to_string(tcount) + "." + GetFileExtension(turl));
		}
		else
		{
			myDownloadFile(thePath, turl, "(" + pubDate + ")" + title + "_" + std::to_string(tcount) + "." + GetFileExtension(turl));
		}
		tcount++;
	}
	/*
	 单个下载END
	*/ 


	/*
	下载所有STR
	*/
	std::cout << "正在获取名称…" << std::endl;
	std::string theName = getArtistName(targetUrl);

	std::vector<std::string> aurls;
	int count = 1;
	extractArticalLink(targetUrl, aurls);
	myCreateDirectory(theName);
	std::cout << "获取列表完毕，开始抓取稿件：" << std::endl;
	for (const auto& url : aurls) {
		std::cout << "正在获取第"  << count <<"篇稿件" << std::endl;
		count++;
		targetUrl = domain + url;
		std::string title;
		std::string pubDate;
		std::string content;
		std::vector<std::string> urls;
		extractTitleAndURL(targetUrl, title, pubDate, content, urls);
		title = ReplaceInvalidChars(title);
		pubDate = RemoveLastCharacters(pubDate,9);
		std::string thePath;
		if (dlmode == "0") {
			thePath = ReplaceInvalidChars(theName) + "\\(" + pubDate + ")" + title;
		}
		else {
			thePath = ReplaceInvalidChars(theName);
		}
		myCreateDirectory(thePath);
		if (dlmode == "0") {
			myCreateFile(thePath, "ReadMe.txt", content);
		}
		int tcount = 1;
		for (const auto& turl : urls) {
			std::cout << "正在下载第" << tcount << "张图片" << std::endl;
			if (dlmode == "0"){
				myDownloadFile(thePath, turl, std::to_string(tcount) + "." + GetFileExtension(turl));}
			else
			{
				myDownloadFile(thePath, turl, "(" + pubDate + ")" + title + "_" + std::to_string(tcount) + "." + GetFileExtension(turl));
			}
			tcount++;
		}

	}
	/*
	下载所有END
	*/

	std::cout << "下载完成，Press Enter to Exit";
	std::getline(std::cin, theName);


	return 0;
}
