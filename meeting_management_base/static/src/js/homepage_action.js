/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@smartdz/owl";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

function debounce(fn, wait) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

function parseOdooDatetimeToLocal(dt) {
  if (!dt) return null;
  try {
    if (typeof dt !== 'string') return null;

    const humanTimeRegex = /([APap][Mm])|[A-Za-z]{3,}/;
    if (humanTimeRegex.test(dt) && !dt.includes('T') && !dt.includes('+') && !dt.endsWith('Z')) {
      return null;
    }

    if (dt.includes('T') || dt.endsWith('Z') || dt.includes('+')) {
      return new Date(dt);
    }
    const clean = dt.replace(/\.\d+/, '').replace(' ', 'T') + 'Z';
    return new Date(clean);
  } catch (e) {
    console.warn('Failed to parse datetime:', dt, e);
    return null;
  }
}

function formatTimeLocal(dateObj, options = { hour: '2-digit', minute: '2-digit', hour12: true }) {
  if (!dateObj) return null;
  try {
    return dateObj.toLocaleTimeString('en-US', options);
  } catch (e) {
    return null;
  }
}

export class MeetingsHome extends Component {
  static template = "meeting_management_base.MeetingsHome";

  setup() {
    this.orm = useService('orm');
    this.action = useService('action');
    this.notification = useService('notification');

    this.state = useState({
      loading: true,
      firstLoad: true,
      creating: false,
      refreshing: false,
      searchQuery: '',

      kpis: { upcoming: 0, today: 0, today_hours: 0, rooms_free: 0, total_participants: 0, upcoming_trend: null },

      upcoming: [],
      filteredUpcoming: [],
      rooms: [],
      feed: [],

      quickCreate: { title: '', date: '', duration: 1, room_id: '' },

      weekStats: { total: 0, hours: 0, avg_duration: 0 },

      analyticsData: { daily_meetings: [], duration_distribution: {}, room_utilization: 0, participant_trends: [] },

      roomPagination: { currentPage: 1, itemsPerPage: 3, totalPages: 1 },

      currentDate: new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }),

      currentView: 'analytics',
      currentSlide: 0,

      calendarMonth: new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' }),
      calendarDays: [],
      selectedDate: new Date(),

      openMenuId: null,
      chartJsLoaded: false,
    });

    this.charts = { meetings: null, duration: null, room: null, participants: null };

    this.refreshInterval = null;
    this.carouselInterval = null;
    this.clickHandler = null;

    this._loadDebounced = debounce((silent) => this._load(silent), 300);
    this._searchDebounced = debounce(() => this._filterMeetings(), 300);

    // Bind methods
    this.setView = this.setView.bind(this);
    this.refresh = this.refresh.bind(this);
    this.onSearch = this.onSearch.bind(this);
    this.clearSearch = this.clearSearch.bind(this);
    this.filterByKpi = this.filterByKpi.bind(this);
    this.nextSlide = this.nextSlide.bind(this);
    this.previousSlide = this.previousSlide.bind(this);
    this.goToSlide = this.goToSlide.bind(this);
    this.quickCreate = this.quickCreate.bind(this);
    this.quickBookRoom = this.quickBookRoom.bind(this);
    this.toggleMeetingMenu = this.toggleMeetingMenu.bind(this);
    this.openMeeting = this.openMeeting.bind(this);
    this.openAllMeetings = this.openAllMeetings.bind(this);
    this.generateCalendar = this.generateCalendar.bind(this);
    this.previousMonth = this.previousMonth.bind(this);
    this.nextMonth = this.nextMonth.bind(this);
    this.goToToday = this.goToToday.bind(this);
    this.selectDay = this.selectDay.bind(this);
    this.renderCharts = this.renderCharts.bind(this);
    this.getPaginatedRooms = this.getPaginatedRooms.bind(this);
    this.updateRoomPagination = this.updateRoomPagination.bind(this);
    this.nextRoomPage = this.nextRoomPage.bind(this);
    this.previousRoomPage = this.previousRoomPage.bind(this);
    this.goToRoomPage = this.goToRoomPage.bind(this);

    onWillStart(async () => {
      // Load Chart.js from CDN
      try {
        await loadJS('https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js');
        this.state.chartJsLoaded = true;
      } catch (error) {
        console.error('Failed to load Chart.js:', error);
      }

      await this._load();
      this.setDefaultDateTime();
      this.generateCalendar();
      this.state.firstLoad = false;
    });

    onMounted(() => {
      // Auto-refresh every 5 minutes
      this.refreshInterval = setInterval(() => {
        this._loadDebounced(true);
      }, 5 * 60 * 1000);

      // Carousel auto-advance every 5 seconds
      this.carouselInterval = setInterval(() => {
        if (this.state.currentView === 'overview') {
          this.nextSlide();
        }
      }, 5000);

      // Render charts if in analytics view
      if (this.state.currentView === 'analytics') {
        this.renderCharts();
      }

      // Close dropdowns on outside click
      this.clickHandler = (e) => {
        if (!e.target.closest('.meeting-actions')) {
          this.state.openMenuId = null;
        }
      };
      document.addEventListener('click', this.clickHandler);
    });

    onWillUnmount(() => {
      if (this.refreshInterval) {
        clearInterval(this.refreshInterval);
        this.refreshInterval = null;
      }

      if (this.carouselInterval) {
        clearInterval(this.carouselInterval);
        this.carouselInterval = null;
      }

      if (this.clickHandler) {
        document.removeEventListener('click', this.clickHandler);
        this.clickHandler = null;
      }

      Object.values(this.charts).forEach(chart => {
        if (chart) chart.destroy();
      });
    });
  }

  setDefaultDateTime() {
    const now = new Date();
    // Round to next hour
    now.setMinutes(0, 0, 0);
    now.setHours(now.getHours() + 1);

    // Format for datetime-local input (YYYY-MM-DDTHH:mm)
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');

    this.state.quickCreate.date = `${year}-${month}-${day}T${hours}:${minutes}`;
  }

  async _load(silent = false) {
    if (!silent) {
      this.state.loading = true;
    }

    try {
      const [kpiRes, upcoming, rooms, feed, weekStats, analyticsData] = await Promise.all([
        this.orm.call('dw.planification.meeting', 'get_dashboard_kpis', []),
        this.orm.call('dw.planification.meeting', 'get_upcoming_meetings', [20]),
        this.orm.call('dw.room', 'get_rooms_availability', []),
        this.orm.call('dw.planification.meeting', 'get_activity_feed', [15]),
        this.orm.call('dw.planification.meeting', 'get_week_stats', []),
        this.orm.call('dw.planification.meeting', 'get_analytics_data', [])
      ]);

      this.state.kpis = kpiRes || this.state.kpis;
      this.state.upcoming = upcoming || [];
      this.state.filteredUpcoming = upcoming || [];
      this.state.feed = feed || [];
      this.state.weekStats = weekStats || this.state.weekStats;
      this.state.analyticsData = analyticsData || this.state.analyticsData;

      this.state.rooms = (rooms || []).map(r => {
        // IMPROVED: More robust field detection
        const dtString = r.free_until || r.busy_until || r.free_till ||
                         r.free_until_datetime || r.available_until ||
                         r.free_until_time || null;

        const looksHuman = typeof dtString === 'string' &&
                           (/([APap][Mm])|[A-Za-z]{3,}/).test(dtString) &&
                           !dtString.includes('T') &&
                           !dtString.includes('+') &&
                           !dtString.endsWith('Z');

        let freeUntilDate = null;
        let computedLocal = null;

        if (dtString && !looksHuman) {
            freeUntilDate = parseOdooDatetimeToLocal(dtString);
            computedLocal = freeUntilDate ? formatTimeLocal(freeUntilDate) : null;
        }

        // IMPROVED: Don't override backend-provided formatted times
        const display_free_until = looksHuman ? dtString :
                                   (r.free_until || r.busy_until || computedLocal || dtString || null);

        return {
            ...r,
            free_until_date: freeUntilDate,
            free_until_local: computedLocal,
            display_free_until,
            // Keep original fields from backend
            free_until: r.free_until,
            busy_until: r.busy_until,
        };
      });

      if (window && window.console) {
        console.debug('Loaded rooms (post-normalize):', this.state.rooms);
      }

      this.updateRoomPagination();

      if (this.state.currentView === 'analytics' && this.state.chartJsLoaded) {
        setTimeout(() => this.renderCharts(), 100);
      }

      if (!silent && !this.state.firstLoad) {
        this.notification.add('Dashboard refreshed successfully', {
          type: 'success',
        });
      }
    } catch (err) {
      console.error('Dashboard load failed:', err);
      this.notification.add('Unable to load dashboard data', {
        type: 'danger',
        title: 'Error'
      });
    } finally {
      if (!silent) {
        this.state.loading = false;
      }
      this.state.refreshing = false;
    }
  }

  async refresh() {
    this.state.refreshing = true;
    await this._load(false);
  }

  setView(view) {
    this.state.currentView = view;

    if (view === 'analytics' && this.state.chartJsLoaded) {
      setTimeout(() => this.renderCharts(), 100);
    }

    if (view === 'calendar') {
      this.generateCalendar();
    }
  }

  onSearch() {
    this._searchDebounced();
  }

  _filterMeetings() {
    const query = this.state.searchQuery.toLowerCase().trim();

    if (!query) {
      this.state.filteredUpcoming = this.state.upcoming;
      return;
    }

    this.state.filteredUpcoming = this.state.upcoming.filter(m =>
      m.name?.toLowerCase().includes(query) ||
      m.organizer_name?.toLowerCase().includes(query) ||
      m.room_name?.toLowerCase().includes(query)
    );
  }

  clearSearch() {
    this.state.searchQuery = '';
    this.state.filteredUpcoming = this.state.upcoming;
  }

  nextSlide() {
    this.state.currentSlide = (this.state.currentSlide + 1) % 2; // Only 2 slides now
  }

  previousSlide() {
    this.state.currentSlide = (this.state.currentSlide - 1 + 2) % 2;
  }

  goToSlide(index) {
    this.state.currentSlide = index;
  }

  async quickCreate() {
    const { title, date, duration, room_id } = this.state.quickCreate;

    // Validation
    if (!title?.trim()) {
        this.notification.add('Please enter a meeting title', {
            type: 'warning',
            title: 'Missing Information'
        });
        return;
    }

    if (!date) {
        this.notification.add('Please select a date and time', {
            type: 'warning',
            title: 'Missing Information'
        });
        return;
    }

    if (duration <= 0) {
        this.notification.add('Duration must be greater than 0', {
            type: 'warning',
            title: 'Invalid Duration'
        });
        return;
    }

    // IMPROVED: Better timezone handling with validation
    let formattedDate;
    try {
        const localDate = new Date(date);

        // Validate the date is valid
        if (isNaN(localDate.getTime())) {
            throw new Error('Invalid date');
        }

        // Convert to UTC for Odoo
        const year = localDate.getUTCFullYear();
        const month = String(localDate.getUTCMonth() + 1).padStart(2, '0');
        const day = String(localDate.getUTCDate()).padStart(2, '0');
        const hours = String(localDate.getUTCHours()).padStart(2, '0');
        const minutes = String(localDate.getUTCMinutes()).padStart(2, '0');
        const seconds = '00';

        formattedDate = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    } catch (e) {
        console.error('Date formatting error:', e);
        this.notification.add('Invalid date format', {
            type: 'danger',
            title: 'Error'
        });
        return;
    }

    const payload = {
        name: title.trim(),
        planned_start_datetime: formattedDate,
        duration: parseFloat(duration),
        room_id: room_id ? parseInt(room_id) : false
    };

    this.state.creating = true;

    try {
        const result = await this.orm.call('dw.planification.meeting', 'quick_create_meeting', [payload]);

        this.notification.add(`Meeting "${title}" created successfully`, {
            type: 'success',
            title: 'Success'
        });

        // Reset form
        this.state.quickCreate = { title: '', date: '', duration: 1, room_id: '' };
        this.setDefaultDateTime();

        // Reload data
        await this._load(true);

        // Open meeting if created successfully
        if (result?.id) {
            setTimeout(() => this.openMeeting(result.id), 500);
        }
    } catch (e) {
        console.error('Quick create failed:', e);
        let errorMsg = 'Failed to create meeting. Please try again.';
        if (e.data && e.data.message) {
            errorMsg = e.data.message;
        } else if (e.message) {
            errorMsg = e.message;
        }
        this.notification.add(errorMsg, {
            type: 'danger',
            title: 'Error'
        });
    } finally {
        this.state.creating = false;
    }
  }

  async quickBookRoom(roomId) {
    try {
        const room = this.state.rooms.find(r => r.id === roomId);

        if (!room.is_free) {
            this.notification.add(`${room?.name || 'Room'} is currently occupied`, {
                type: 'warning',
                title: 'Room Unavailable'
            });
            return;
        }

        this.notification.add(`Booking ${room?.name || 'room'}...`, {
            type: 'info'
        });

        // Get current time and convert to UTC
        const now = new Date();

        const year = now.getUTCFullYear();
        const month = String(now.getUTCMonth() + 1).padStart(2, '0');
        const day = String(now.getUTCDate()).padStart(2, '0');
        const hours = String(now.getUTCHours()).padStart(2, '0');
        const minutes = String(now.getUTCMinutes()).padStart(2, '0');
        const seconds = String(now.getUTCSeconds()).padStart(2, '0');
        const odooDateTime = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;

        const payload = {
            name: `Quick Booking - ${room?.name || 'Room'}`,
            planned_start_datetime: odooDateTime,
            duration: 1,
            room_id: roomId
        };

        const result = await this.orm.call('dw.planification.meeting', 'quick_create_meeting', [payload]);

        this.notification.add(`${room?.name || 'Room'} booked successfully for 1 hour`, {
            type: 'success',
            title: 'Room Booked'
        });

        await this._load(true);

        if (result?.id) {
            setTimeout(() => this.openMeeting(result.id), 300);
        }
    } catch (err) {
        console.error('Room booking failed:', err);
        let errorMsg = 'Failed to book room. It may no longer be available.';
        if (err.data && err.data.message) {
            errorMsg = err.data.message;
        }
        this.notification.add(errorMsg, {
            type: 'danger',
            title: 'Booking Failed'
        });
    }
  }

  toggleMeetingMenu(meetingId, event) {
    event.stopPropagation();
    this.state.openMenuId = this.state.openMenuId === meetingId ? null : meetingId;
  }

  async openMeeting(id) {
    try {
      await this.action.doAction({
        type: 'ir.actions.act_window',
        res_model: 'dw.planification.meeting',
        res_id: id,
        views: [[false, 'form']],
        target: 'current'
      });
    } catch (err) {
      console.error('Failed to open meeting:', err);
      this.notification.add('Failed to open meeting', { type: 'danger' });
    }
  }

  async openAllMeetings() {
    try {
      await this.action.doAction({
        type: 'ir.actions.act_window',
        res_model: 'dw.planification.meeting',
        views: [[false, 'list'], [false, 'form']],
        target: 'current',
        domain: []
      });
    } catch (err) {
      console.error('Failed to open meetings:', err);
      this.notification.add('Failed to open meetings', { type: 'danger' });
    }
  }

  getPaginatedRooms() {
    const { currentPage, itemsPerPage } = this.state.roomPagination;
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    return this.state.rooms.slice(startIndex, endIndex);
  }

  updateRoomPagination() {
    const totalRooms = this.state.rooms.length;
    const { itemsPerPage } = this.state.roomPagination;

    const totalPages = Math.max(1, Math.ceil(totalRooms / itemsPerPage));

    this.state.roomPagination.totalPages = totalPages;

    if (this.state.roomPagination.currentPage > totalPages) {
      this.state.roomPagination.currentPage = totalPages;
    }

    if (this.state.roomPagination.currentPage < 1) {
      this.state.roomPagination.currentPage = 1;
    }
  }

  nextRoomPage() {
    const { currentPage, totalPages } = this.state.roomPagination;
    if (currentPage < totalPages) {
      this.state.roomPagination.currentPage++;
    }
  }

  previousRoomPage() {
    if (this.state.roomPagination.currentPage > 1) {
      this.state.roomPagination.currentPage--;
    }
  }

  goToRoomPage(page) {
    const { totalPages } = this.state.roomPagination;
    if (page >= 1 && page <= totalPages) {
      this.state.roomPagination.currentPage = page;
    }
  }

  generateCalendar() {
    const date = new Date(this.state.selectedDate);
    const year = date.getFullYear();
    const month = date.getMonth();

    this.state.calendarMonth = date.toLocaleDateString('en-US', {
        month: 'long',
        year: 'numeric'
    });

    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const prevLastDay = new Date(year, month, 0);

    const firstDayOfWeek = firstDay.getDay();
    const lastDateOfMonth = lastDay.getDate();
    const prevLastDate = prevLastDay.getDate();

    const days = [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // Previous month days
    for (let i = firstDayOfWeek - 1; i >= 0; i--) {
        const day = prevLastDate - i;
        const dayDate = new Date(year, month - 1, day);
        dayDate.setHours(0, 0, 0, 0);

        // FIXED: Format date manually to avoid timezone conversion
        const dateYear = dayDate.getFullYear();
        const dateMonth = String(dayDate.getMonth() + 1).padStart(2, '0');
        const dateDay = String(dayDate.getDate()).padStart(2, '0');
        const dateString = `${dateYear}-${dateMonth}-${dateDay}`;

        days.push({
            day,
            date: dateString,
            isOtherMonth: true,
            isToday: false,
            hasEvents: false,
            eventCount: 0
        });
    }

    // Current month days
    for (let day = 1; day <= lastDateOfMonth; day++) {
        const dayDate = new Date(year, month, day);
        dayDate.setHours(0, 0, 0, 0);
        const isToday = dayDate.getTime() === today.getTime();

        // FIXED: Format date manually to avoid timezone conversion
        const dateYear = dayDate.getFullYear();
        const dateMonth = String(dayDate.getMonth() + 1).padStart(2, '0');
        const dateDay = String(dayDate.getDate()).padStart(2, '0');
        const dateString = `${dateYear}-${dateMonth}-${dateDay}`;

        // Count events for this day correctly - compare LOCAL dates
        const eventCount = this.state.upcoming.filter(m => {
            if (!m.planned_start_datetime) return false;

            // Parse the meeting datetime
            const mDate = new Date(m.planned_start_datetime);

            // Create a date at midnight in LOCAL timezone for comparison
            const meetingDay = new Date(mDate.getFullYear(), mDate.getMonth(), mDate.getDate());
            meetingDay.setHours(0, 0, 0, 0);

            // Compare timestamps
            return meetingDay.getTime() === dayDate.getTime();
        }).length;

        days.push({
            day,
            date: dateString,
            isOtherMonth: false,
            isToday,
            hasEvents: eventCount > 0,
            eventCount
        });
    }

    // Next month days
    const remainingDays = 42 - days.length;
    for (let day = 1; day <= remainingDays; day++) {
        const dayDate = new Date(year, month + 1, day);
        dayDate.setHours(0, 0, 0, 0);

        // FIXED: Format date manually to avoid timezone conversion
        const dateYear = dayDate.getFullYear();
        const dateMonth = String(dayDate.getMonth() + 1).padStart(2, '0');
        const dateDay = String(dayDate.getDate()).padStart(2, '0');
        const dateString = `${dateYear}-${dateMonth}-${dateDay}`;

        days.push({
            day,
            date: dateString,
            isOtherMonth: true,
            isToday: false,
            hasEvents: false,
            eventCount: 0
        });
    }

    this.state.calendarDays = days;
  }

  previousMonth() {
    const date = new Date(this.state.selectedDate);
    date.setMonth(date.getMonth() - 1);
    this.state.selectedDate = date;
    this.generateCalendar();
  }

  nextMonth() {
    const date = new Date(this.state.selectedDate);
    date.setMonth(date.getMonth() + 1);
    this.state.selectedDate = date;
    this.generateCalendar();
  }

  goToToday() {
    this.state.selectedDate = new Date();
    this.generateCalendar();
  }

  selectDay(day) {
    // FIXED: Parse the date correctly without timezone issues
    // The day.date is in format "YYYY-MM-DD"
    const [year, month, dayNum] = day.date.split('-').map(Number);

    // Create date in LOCAL timezone (not UTC)
    const selectedDate = new Date(year, month - 1, dayNum);
    selectedDate.setHours(0, 0, 0, 0);

    this.state.filteredUpcoming = this.state.upcoming.filter(m => {
        if (!m.planned_start_datetime) return false;

        // Parse meeting datetime
        const mDate = new Date(m.planned_start_datetime);

        // Create comparison date in LOCAL timezone
        const meetingDay = new Date(mDate.getFullYear(), mDate.getMonth(), mDate.getDate());
        meetingDay.setHours(0, 0, 0, 0);

        // Compare timestamps
        return meetingDay.getTime() === selectedDate.getTime();
    });

    this.state.currentView = 'overview';
    this.state.currentSlide = 0;

    // Format date for display
    const displayDate = selectedDate.toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });

    this.notification.add(`Showing meetings for ${displayDate}`, {
        type: 'info'
    });
  }

  filterByKpi(type) {
    this.state.currentView = 'overview';
    this.state.currentSlide = 0;

    const now = new Date();
    // Create today at midnight in LOCAL timezone
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    today.setHours(0, 0, 0, 0);

    if (type === 'today') {
        this.state.filteredUpcoming = this.state.upcoming.filter(m => {
            if (!m.planned_start_datetime) return false;

            const meetingDate = new Date(m.planned_start_datetime);
            // Create meeting day at midnight in LOCAL timezone
            const meetingDay = new Date(meetingDate.getFullYear(), meetingDate.getMonth(), meetingDate.getDate());
            meetingDay.setHours(0, 0, 0, 0);

            return meetingDay.getTime() === today.getTime();
        });
    } else if (type === 'upcoming') {
        this.state.filteredUpcoming = this.state.upcoming;
    }

    this.notification.add(`Filtered to show ${type} meetings`, {
        type: 'info'
    });
  }

  renderCharts() {
    if (!this.state.chartJsLoaded || !window.Chart) {
      console.warn('Chart.js not loaded');
      return;
    }

    // IMPROVED: Check for required DOM elements first
    const requiredElements = [
      'meetingsChart',
      'durationChart',
      'roomChart',
      'participantChart'
    ];

    const allElementsReady = requiredElements.every(id =>
      document.getElementById(id) !== null
    );

    if (!allElementsReady) {
      console.warn('Chart elements not ready, retrying...');
      setTimeout(() => this.renderCharts(), 200);
      return;
    }

    setTimeout(() => {
      this.drawMeetingsChart();
      this.drawDurationChart();
      this.drawRoomChart();
      this.drawParticipantChart();
    }, 100);
  }

  drawMeetingsChart() {
    const canvas = document.getElementById('meetingsChart');
    if (!canvas) return;

    if (this.charts.meetings) {
      this.charts.meetings.destroy();
    }

    const data = this.state.analyticsData.daily_meetings || [0, 0, 0, 0, 0, 0, 0];

    this.charts.meetings = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        datasets: [{
          label: 'Meetings',
          data: data,
          backgroundColor: '#3b82f6',
          borderRadius: 8,
          borderSkipped: false,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            backgroundColor: '#0f172a',
            padding: 12,
            titleColor: '#fff',
            bodyColor: '#fff',
            borderColor: '#3b82f6',
            borderWidth: 1,
            displayColors: false,
            callbacks: {
              label: (context) => `${context.parsed.y} meetings`
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              stepSize: 2,
              color: '#64748b'
            },
            grid: {
              color: '#e2e8f0',
              drawBorder: false
            }
          },
          x: {
            ticks: {
              color: '#64748b'
            },
            grid: {
              display: false
            }
          }
        }
      }
    });
  }

  drawDurationChart() {
    const canvas = document.getElementById('durationChart');
    if (!canvas) return;

    if (this.charts.duration) {
      this.charts.duration.destroy();
    }

    const dist = this.state.analyticsData.duration_distribution || {
      under_30: 15,
      '30_to_60': 45,
      '60_to_120': 30,
      over_120: 10
    };

    const data = [
      dist.under_30 || 0,
      dist['30_to_60'] || 0,
      dist['60_to_120'] || 0,
      dist.over_120 || 0
    ];

    this.charts.duration = new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: ['< 30m', '30-60m', '1-2h', '> 2h'],
        datasets: [{
          data: data,
          backgroundColor: ['#10b981', '#3b82f6', '#f59e0b', '#ef4444'],
          borderWidth: 0,
          spacing: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              padding: 16,
              usePointStyle: true,
              font: {
                size: 12,
                family: 'Inter'
              }
            }
          },
          tooltip: {
            backgroundColor: '#0f172a',
            padding: 12,
            displayColors: false,
            callbacks: {
              label: (context) => `${context.label}: ${context.parsed}%`
            }
          }
        }
      }
    });
  }

  drawRoomChart() {
    const canvas = document.getElementById('roomChart');
    if (!canvas) return;

    if (this.charts.room) {
      this.charts.room.destroy();
    }

    const utilized = this.state.analyticsData.room_utilization || 0;
    const available = 100 - utilized;

    this.charts.room = new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: ['Utilized', 'Available'],
        datasets: [{
          data: [utilized, available],
          backgroundColor: ['#3b82f6', '#e0f2fe'],
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '75%',
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            backgroundColor: '#0f172a',
            padding: 12,
            displayColors: false,
            callbacks: {
              label: (context) => `${context.label}: ${context.parsed}%`
            }
          }
        }
      },
      plugins: [{
        id: 'centerText',
        afterDraw: (chart) => {
          const { ctx, chartArea: { width, height } } = chart;
          ctx.save();
          ctx.font = 'bold 32px Inter';
          ctx.fillStyle = '#0f172a';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(`${utilized}%`, width / 2, height / 2);
          ctx.font = '14px Inter';
          ctx.fillStyle = '#64748b';
          ctx.fillText('Utilized', width / 2, height / 2 + 25);
          ctx.restore();
        }
      }]
    });
  }

  drawParticipantChart() {
    const canvas = document.getElementById('participantChart');
    if (!canvas) return;

    if (this.charts.participants) {
      this.charts.participants.destroy();
    }

    const data = this.state.analyticsData.participant_trends || [0, 0, 0, 0, 0, 0, 0];

    this.charts.participants = new Chart(canvas, {
      type: 'line',
      data: {
        labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        datasets: [{
          label: 'Avg Participants',
          data: data,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: '#3b82f6',
          pointBorderColor: '#fff',
          pointBorderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            backgroundColor: '#0f172a',
            padding: 12,
            displayColors: false,
            callbacks: {
              label: (context) => `${context.parsed.y} participants`
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              stepSize: 5,
              color: '#64748b'
            },
            grid: {
              color: '#e2e8f0',
              drawBorder: false
            }
          },
          x: {
            ticks: {
              color: '#64748b'
            },
            grid: {
              display: false
            }
          }
        }
      }
    });
  }
}

registry.category('actions').add('dw_meeting.home', MeetingsHome);