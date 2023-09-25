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


//�������UTF8�ַ���ת��ΪGBK����
//WindowsAPI
std::string convertUTF8ToGBK(const std::string& utf8String) {
	int wideLength = MultiByteToWideChar(CP_UTF8, 0, utf8String.c_str(), -1, nullptr, 0);
	if (wideLength == 0) {
		std::cerr << "�޷���ȡ���ַ��ַ������ȣ�" << std::endl;
		return "";
	}

	wchar_t* wideBuffer = new wchar_t[wideLength];
	MultiByteToWideChar(CP_UTF8, 0, utf8String.c_str(), -1, wideBuffer, wideLength);

	int gbkLength = WideCharToMultiByte(CP_ACP, 0, wideBuffer, -1, nullptr, 0, nullptr, nullptr);
	if (gbkLength == 0) {
		std::cerr << "�޷���ȡGBK�����ַ������ȣ�" << std::endl;
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

//�������GBK�ַ���ת��UTF8Ϊ����
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


// �ص�����������д���ļ�
// �ṹ�����ڱ��������Ϣ
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
		// ���ļ�
		std::ofstream file(filePath, std::ios::binary);
		if (!file) {
			std::cout << "�޷����ļ���" << filePath << std::endl;
			return false;
		}

		std::string tpox = theip + ":" + theport;

		// ����Curlѡ��
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

		// ���ý��Ȼص�����
		curl_easy_setopt(curl, CURLOPT_NOPROGRESS, FALSE);
		curl_easy_setopt(curl, CURLOPT_PROGRESSFUNCTION, progress_func);
		printf("]\r");

		// ִ������
		CURLcode res = curl_easy_perform(curl);

		int count = 0;
		// ��������Ƿ�ɹ�
		while (res != CURLE_OK) {
			count++;
			if (count == 5) {
				return !true;
			}
			std::cout << "����ʧ�ܣ�" << curl_easy_strerror(res) << std::endl;
			std::cout << "���ԡ���" << count << "/5��" << std::endl;
			res = curl_easy_perform(curl);
		}

		// ����Curl��Դ
		curl_easy_cleanup(curl);

		// �ر��ļ�
		file.close();

		std::cout << "�ļ����سɹ���" << filePath << std::endl;
		return true;
	}

	return false;
}

// �ص����������ڴ���HTTP����ķ�������
size_t WriteCallback(char* contents, size_t size, size_t nmemb, std::string* output) {
	size_t totalSize = size * nmemb;
	output->append(contents, totalSize);
	return totalSize;
}

// ��ȡָ����ַ��ҳ������
std::string getPageContent(const std::string& url) {
	std::string response;

	// ��ʼ��libcurl
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

// ��ȡ��ҳ�����е�artist_name
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

// ��ȡartist_name
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

//���ڽ�HTMLת���ַ�ת����ԭ��
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
				// ��Ӹ���ת���ַ��Ĵ����߼�

				pos = endPos + 1;
				continue;
			}
		}

		result += input[pos];
		pos++;
	}

	return result;
}

//��������ַ����Ļ��б��\n
//������
void replaceNewlines(std::string& str) {
	size_t found = str.find('\n');
	while (found != std::string::npos) {
		str.replace(found, 1, "\\n");
		found = str.find('\n', found + 2); // �ҵ���һ�����з�
	}
}

//��������ַ���д�뵽����Ŀ¼�µ�out.txt
//������
void writeToFile(const std::string& content) {
	std::ofstream outputFile("out.txt");

	if (outputFile.is_open()) {
		outputFile << content;
		outputFile.close();
		std::cout << "д���ļ��ɹ���" << std::endl;
	}
	else {
		std::cerr << "�޷����ļ���" << std::endl;
	}
}

//vectorȥ��
void removeDuplicates(std::vector<std::string>& urls) {
	std::unordered_set<std::string> uniqueUrls;
	std::vector<std::string> result;

	for (const std::string& url : urls) {
		if (uniqueUrls.find(url) == uniqueUrls.end()) {
			// ��ǰԪ���ڼ����в����ڣ���ӵ����������ΨһԪ�ؼ���
			result.push_back(url);
			uniqueUrls.insert(url);
		}
	}

	urls = result;
}

//�滻�Ƿ�Windows�ַ�
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

//������д���ļ�
bool myCreateFile(const std::string& relativePath, const std::string& fileName, const std::string& content)
{
	// �����������ļ�·��
	std::filesystem::path filePath(convertUTF8ToGBK(relativePath));

	filePath /= fileName;

	// ���ļ�������д��
	std::ofstream file(filePath);
	if (file.is_open())
	{
		file << content;
		file.close();
		std::cout << "�ļ������ɹ���" << fileName << std::endl;
		return true;
	}
	else
	{
		std::cout << "�ļ�����ʧ�ܣ�" << fileName << std::endl;
		return false;
	}
}

//�����ļ���
//WindowsAPI
bool CreateDirectoryRecursive(const std::wstring& path)
{
	if (::CreateDirectoryW(path.c_str(), NULL) || ::GetLastError() == ERROR_ALREADY_EXISTS)
	{
		std::wcout << L"�ļ��д����ɹ�" << std::endl;
		return true;
	}
	else
	{
		DWORD lastError = ::GetLastError();
		if (lastError == ERROR_PATH_NOT_FOUND)
		{
			// �ݹ鴴���ϼ�Ŀ¼
			size_t pos = path.find_last_of(L"\\/");
			if (pos != std::wstring::npos)
			{
				std::wstring parentPath = path.substr(0, pos);
				if (CreateDirectoryRecursive(parentPath))
				{
					// �����ϼ�Ŀ¼�ɹ����ٴγ��Դ�����ǰĿ¼
					return CreateDirectoryRecursive(path);
				}
				else
				{
					return false;
				}
			}
		}

		std::wcerr << L"�ļ��д���ʧ��: " << path << std::endl;
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

//��ȡ��׺��
std::string GetFileExtension(const std::string& downloadLink)
{
	std::string fileExtension;

	// �ҵ����һ��б�ܵ�λ��
	size_t lastSlashPos = downloadLink.find_last_of("/");
	if (lastSlashPos != std::string::npos)
	{
		// ��ȡ�ļ���
		std::string fileName = downloadLink.substr(lastSlashPos + 1);

		// �ҵ����һ�����λ��
		size_t lastDotPos = fileName.find_last_of(".");
		if (lastDotPos != std::string::npos && lastDotPos != fileName.length() - 1)
		{
			// ��ȡ��׺��
			fileExtension = fileName.substr(lastDotPos + 1);
		}
	}

	return fileExtension;
}

//��β��ɾ�ַ�
std::string RemoveLastCharacters(const std::string& str, size_t n)
{
	if (n >= str.length()) {
		return "";
	}

	return str.substr(0, str.length() - n);
}

// ��ȡ�������ݺ�URL
void extractTitleAndURL(const std::string& url, std::string& title, std::string& pubDate, std::string& content, std::vector<std::string>& urls) {
	std::string response;
	response = getPageContent(url);
	//response = convertUTF8ToGBK(response);
	response = unescapeHTML(response);
	//replaceNewlines(response);
	//writeToFile(response);

	// ��ȡ��������
	std::regex titleRegex("<h1 class=\"post__title\">\n            <span>(.*?)</span> <span>((.*?))</span>\n        </h1>");
	std::smatch titleMatch;
	if (std::regex_search(response, titleMatch, titleRegex) && titleMatch.size() > 1) {
		title = titleMatch[1].str();
	}

	// ��ȡ����ʱ��
	std::regex pubDateRegex("<meta name=\"published\" content=\"(.*?)\">");
	std::smatch pubDateMatch;
	if (std::regex_search(response, pubDateMatch, pubDateRegex) && pubDateMatch.size() > 1) {
		pubDate = pubDateMatch[1].str();
	}

	// ��ȡ˵������
	std::regex contentRegex("<h2>Content</h2>\n    <div class=\"post__content\">\n<pre>([\\s\\S]*?)</pre>\n    </div>");
	std::smatch contentMatch;
	if (std::regex_search(response, contentMatch, contentRegex) && contentMatch.size() > 1) {
		content = contentMatch[1].str();
	}

	// ��ȡ��ʽΪ<a class="fileThumb" href="#url" download="#filename">��URL����
	std::regex urlRegex("<a\n              class=\"fileThumb\"\n              href=\"(.*?)\"\n              download=\".*?\"\n            >");
	std::sregex_iterator urlIterator(response.begin(), response.end(), urlRegex);
	std::sregex_iterator endIterator;
	for (; urlIterator != endIterator; ++urlIterator) {
		urls.push_back((*urlIterator)[1].str());
	}

}
// ��Ŀ¼��ȡͶ��
void extractArticalLink(const std::string& url, std::vector<std::string>& urls) {
	int offset = 0;
	int count = 1;
	std::cout << "��ʼ��ȡĿ¼��" << std::endl;
	std::string fullUrl = url + "?o=" + std::to_string(offset);

	while (true) {
		std::string content = getPageContent(fullUrl);
		if (content.find("Redirecting...") != std::string::npos) {
			// �����������а��� "Redirecting..." ʱ������ѭ��
			break;
		}
		std::cout << "���ڻ�ȡ��" << count << "ҳ" << std::endl;
		count++;
		// ʹ��������ʽ��ȡ���Ӳ���
		std::regex linkRegex(regex);
		std::smatch match;

		// �ڷ��������в���ƥ������Ӳ���ӵ� urls ��
		std::string::const_iterator searchStart(content.cbegin());
		while (std::regex_search(searchStart, content.cend(), match, linkRegex)) {
			urls.push_back(match[4]);
			searchStart = match.suffix().first;
		}

		// ���� offset ֵ��������һ������� URL
		offset += 50;
		fullUrl = url + "?o=" + std::to_string(offset);
	}
}


int main() {
	std::cout << "Ver. 1.2.4" << std::endl;
	//Single�澯��
	//std::cout << "ע�⣺����������ص�ƪͶ��" << std::endl;
	std::cout << "��Ҫʹ��HTTP�����𣿲�ʹ������n��ʹ��������ֱ�ӻس����ɣ�" << std::endl;
	std::getline(std::cin, usepx);
	if (usepx != "n") {
		usepx = "1";
		std::cout << "��ѡ��ʹ��HTTP����" << std::endl;
		std::cout << "������HTTP����ip(����ΪĬ��localhost���Ƽ�)��" << std::endl;
		std::string tip = "";
		std::getline(std::cin, tip);
		std::cout << "������HTTP����˿�(����ΪĬ��10809��10809ΪV2rayNĬ�϶˿ڣ���������Ĵ������ѡ��)��" << std::endl;
		std::string tport = "";
		std::getline(std::cin, tport);
		if (tip != "") { theip = tip; }
		if (tport != "") { theport = tport; }
		tpox = theip + ":" + theport;
		std::cout << "����HTTP�����ַ�ǣ�" << tpox << std::endl;
	}
	std::cout << "�Ƿ�ʹ�ý�ͼƬ����ģʽ����ģʽ�½�ֻ������ͼƬ��������ͼƬ���洢��ͬһĿ¼�¡�ʹ��������y����ʹ�������գ�" << std::endl;
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
	std::cout << "������Ŀ����ַ���벻Ҫ���롰?o=����֮��Ĳ��֣���������޷�����ʶ�𣩣�" << std::endl;
	std::getline(std::cin, targetUrl);

	/*
	 ��������STR
	
	std::string theName = "";
	std::cout << "�������������ƣ�" << std::endl;
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
		std::cout << "�������ص�" << tcount << "��ͼƬ" << std::endl;
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
	 ��������END
	*/ 


	/*
	��������STR
	*/
	std::cout << "���ڻ�ȡ���ơ�" << std::endl;
	std::string theName = getArtistName(targetUrl);

	std::vector<std::string> aurls;
	int count = 1;
	extractArticalLink(targetUrl, aurls);
	myCreateDirectory(theName);
	std::cout << "��ȡ�б���ϣ���ʼץȡ�����" << std::endl;
	for (const auto& url : aurls) {
		std::cout << "���ڻ�ȡ��"  << count <<"ƪ���" << std::endl;
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
			std::cout << "�������ص�" << tcount << "��ͼƬ" << std::endl;
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
	��������END
	*/

	std::cout << "������ɣ�Press Enter to Exit";
	std::getline(std::cin, theName);


	return 0;
}
